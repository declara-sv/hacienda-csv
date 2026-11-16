"""Contract checks and execution tests for the actual workflow shell blocks.

Run: python -m unittest discover -s .github/tests -v
These tests never authenticate to or mutate GCP.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / '.github/workflows'


def workflow(name):
    path = WORKFLOWS / name
    return yaml.load(path.read_text(), Loader=yaml.BaseLoader) if path.exists() else {}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.ci = workflow('ci-api.yml')
        self.deploy = workflow('deploy-api.yml')

    def steps(self):
        self.assertIn('jobs', self.deploy, 'release workflow must exist')
        return self.deploy['jobs']['deploy']['steps']

    def step(self, id):
        return next(step for step in self.steps() if step.get('id') == id)

    def run_step(self, id, env, executables=None):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'output'
            for name, source in (executables or {}).items():
                path = Path(tmp) / name
                path.write_text('#!/usr/bin/env bash\n' + source)
                path.chmod(0o700)
            result = subprocess.run(
                ['bash', '--noprofile', '--norc', '-eo', 'pipefail', '-c', self.step(id)['run']],
                env={**os.environ, 'GITHUB_OUTPUT': str(output), 'PATH': tmp + os.pathsep + os.environ['PATH'], **env},
                text=True, capture_output=True, cwd=tmp)
            return result, output.read_text() if output.exists() else ''

    def test_ci_covers_branches_and_runs_lint_and_tests(self):
        self.assertIn('on', self.ci, 'CI workflow must exist')
        self.assertEqual(self.ci['on']['push']['branches'], ['**'])
        for event in ('push', 'pull_request'):
            for path in ('apps/api/**', '.github/workflows/**', '.github/tests/**'):
                self.assertIn(path, self.ci['on'][event]['paths'])
        self.assertEqual(self.ci['permissions'], {'contents': 'read'})
        job = self.ci['jobs']['test']
        steps = job['steps']
        self.assertTrue(any(s.get('uses', '').startswith('astral-sh/setup-uv@v') for s in steps))
        for command in ('uv sync --locked', 'uv run ruff check .', 'uv run pytest'):
            step = next(s for s in steps if s.get('run') == command)
            self.assertEqual(step['working-directory'], 'apps/api', command)
        commands = '\n'.join(s.get('run', '') for s in steps)
        self.assertIn('python -m unittest discover -s .github/tests -v', commands)

    def test_ci_tests_run_against_postgres_service(self):
        job = self.ci['jobs']['test']
        postgres = job['services']['postgres']
        self.assertEqual(postgres['image'], 'postgres:16')
        self.assertIn('--health-cmd', postgres['options'])
        env = postgres['env']
        pytest = next(s for s in job['steps'] if s.get('run') == 'uv run pytest')
        self.assertEqual(
            pytest['env']['TEST_DATABASE_URL'],
            f"postgresql+psycopg://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
            f"@localhost:{postgres['ports'][0].split(':')[0]}/{env['POSTGRES_DB']}")

    def test_all_jobs_use_blacksmith(self):
        for config in (self.ci, self.deploy):
            self.assertIn('jobs', config)
            for job in config['jobs'].values():
                self.assertEqual(job['runs-on'], 'blacksmith-2vcpu-ubuntu-2404')

    def test_only_tags_release_and_dispatch_requires_tag(self):
        self.assertIn('on', self.deploy)
        self.assertEqual(self.deploy['on']['push'], {'tags': ['api-v*']})
        self.assertEqual(self.deploy['on']['workflow_dispatch']['inputs']['tag']['required'], 'true')
        self.assertFalse((WORKFLOWS / 'deploy-api-cloud-run.yml').exists())
        self.assertEqual(self.deploy['concurrency'],
                         {'group': 'deploy-api', 'cancel-in-progress': 'false', 'queue': 'max'})

    def validated_secrets(self):
        step = next(s for s in self.steps() if s.get('name') == 'Validate Secret Manager versions (metadata only)')
        self.assertIn('gcloud secrets versions describe latest', step['run'])
        self.assertNotIn('versions access', step['run'])
        return step['run'].split('for secret in ', 1)[1].split(';', 1)[0].split()

    def test_tag_validation_rejects_malformed_or_injected_values(self):
        for value in ('main', '', 'api-v1.2', 'api-v01.2.3', 'api-v1.2.3-rc1',
                      'api-v1.2.3\nevil=1', 'api-v1.2.3; touch injected'):
            with self.subTest(tag=value):
                result, output = self.run_step('release', {'RELEASE_TAG': value})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(output, '')
        result, output = self.run_step('release', {'RELEASE_TAG': 'api-v1.2.3'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('tag=api-v1.2.3', output)
        checkout = next(s for s in self.steps() if s.get('uses', '').startswith('actions/checkout@'))
        self.assertEqual(checkout['with']['ref'], 'refs/tags/${{ steps.release.outputs.tag }}')

    def test_configuration_validation_and_secret_scope(self):
        env = {key: 'configured' for key in (
            'GCP_PROJECT_ID', 'GCP_REGION', 'GAR_REPOSITORY', 'CLOUD_RUN_SERVICE', 'API_CLERK_ISSUER',
            'SEC_GCP_WORKLOAD_IDENTITY_PROVIDER', 'SEC_GCP_SERVICE_ACCOUNT')}
        env['API_CLERK_AUTHORIZED_PARTIES'] = ''
        for key in env:
            if key == 'API_CLERK_AUTHORIZED_PARTIES':
                continue
            result, _ = self.run_step('validate', {**env, key: ''})
            self.assertNotEqual(result.returncode, 0, key)
        result, _ = self.run_step('validate', env)
        self.assertEqual(result.returncode, 0, result.stderr)
        # Authorized parties are optional, but must be a JSON list when set.
        for parties, ok in (('["https://app.example.com","https://www.example.com"]', True),
                            ('https://app.example.com', False)):
            result, _ = self.run_step('validate', {**env, 'API_CLERK_AUTHORIZED_PARTIES': parties})
            self.assertEqual(result.returncode == 0, ok, parties)
        text = (WORKFLOWS / 'deploy-api.yml').read_text()
        self.assertEqual(text.count('secrets.API_DATABASE_URL'), 1)
        for retired in ('API_CONNECTION_STRING_POSTGRES', 'secrets.API_JWT_SIGNING_KEY', 'api-jwt-signing-key',
                        'JWT_SIGNING_KEY', 'JWT_ISSUER', 'JWT_AUDIENCE',
                        'secrets.API_STORAGE_AZURE_BLOB_CONNECTION_STRING', 'secrets.API_ANTHROPIC_API_KEY'):
            self.assertNotIn(retired, text)

    def test_manual_dispatch_skips_build_and_migrations(self):
        steps = self.steps()
        for id in ('docker-auth', 'builder', 'build', 'migrate'):
            self.assertEqual(self.step(id)['if'], "github.event_name == 'push'", id)
        for id in ('image', 'deploy'):
            self.assertNotIn('if', self.step(id), id)  # default success() gate
        # Migrations use the resolved digest, and must finish before the deploy.
        order = [steps.index(self.step(id)) for id in ('build', 'image', 'migrate', 'deploy')]
        self.assertEqual(order, sorted(order))
        for id in ('migrate', 'deploy'):
            self.assertNotIn('continue-on-error', self.step(id))
        self.assertFalse(any(s.get('uses', '').startswith('actions/setup-dotnet@') for s in steps))
        migrate = self.step('migrate')
        self.assertEqual(migrate['env']['IMAGE_URI'], '${{ steps.image.outputs.uri }}')
        self.assertIn('docker run --rm -e DATABASE_URL "$IMAGE_URI" alembic upgrade head', migrate['run'])
        result, _ = self.run_step('migrate', {'DATABASE_URL': '', 'IMAGE_URI': 'image@sha256:x'})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing', result.stdout + result.stderr)

    def test_image_resolution_fails_closed_and_uses_existing_digest(self):
        env = {'IMAGE_TAG': 'region-docker.pkg.dev/project/repo/accounting-api:api-v1.2.3',
               'GCP_PROJECT_ID': 'project'}
        for response in ('exit 1', 'echo garbage', 'echo ""'):
            result, output = self.run_step('image', env, {'gcloud': response})
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output, '')
        digest = 'sha256:' + 'a' * 64
        result, output = self.run_step('image', env, {'gcloud': f'echo {digest}'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.strip(), 'uri=' + env['IMAGE_TAG'].rsplit(':', 1)[0] + '@' + digest)

    def test_migration_failure_is_not_swallowed_and_url_stays_out_of_argv(self):
        url = 'postgresql+psycopg://user:spaces ; $literal and "quotes"@host/db'
        image = 'region-docker.pkg.dev/project/repo/accounting-api@sha256:' + 'a' * 64
        script = ('expected=(run --rm -e DATABASE_URL "$IMAGE_URI" alembic upgrade head)\n'
                  '[[ "$*" == "${expected[*]}" && "$*" != *"$DATABASE_URL"* ]] || exit 90\n'
                  '[[ "$DATABASE_URL" == "$EXPECTED_URL" ]] || exit 91\n'
                  'exit 42')
        result, _ = self.run_step('migrate', {'DATABASE_URL': url, 'EXPECTED_URL': url, 'IMAGE_URI': image},
                                  {'docker': script})
        self.assertEqual(result.returncode, 42, result.stderr)
        self.assertNotIn(url, result.stdout + result.stderr)

    def test_release_image_builds_api_and_can_run_migrations(self):
        build = self.step('build')['with']
        self.assertEqual(build['context'], 'apps/api')
        dockerfile = ROOT / build['file']
        self.assertEqual(dockerfile, ROOT / 'apps/api/Dockerfile')
        text = dockerfile.read_text()
        self.assertIn('uv sync --frozen --no-dev', text)
        for copied in ('COPY alembic.ini', 'COPY alembic ', 'COPY app '):
            self.assertIn(copied, text)
        self.assertIn('ENV PATH="/app/.venv/bin:', text)  # `alembic` resolves inside the image
        self.assertRegex(text, r'(?m)^USER (?!root\b)\S+$')
        self.assertIn('${PORT:-8080}', text)

    def test_deploy_uses_digest_and_secret_manager_not_plaintext(self):
        command = self.step('deploy')['run']
        self.assertIn('--image "$IMAGE_URI"', command)
        for env in ('ENVIRONMENT=Production', 'ENABLE_SWAGGER=false', 'WORKER_ENABLED=true',
                    'STORAGE_PROVIDER=${STORAGE_PROVIDER}'):
            self.assertIn(env, command)
        self.assertNotIn('ENABLE_SWAGGER=true', command)
        # The in-process worker needs CPU outside requests and a warm instance.
        self.assertIn('--no-cpu-throttling', command)
        self.assertIn('--min-instances=1', command)
        secrets = dict(item.split('=', 1) for item in
                       command.split('--set-secrets "', 1)[1].split('"', 1)[0].split(','))
        self.assertEqual(secrets, {
            'DATABASE_URL': 'api-database-url:latest',
            'STORAGE_AZURE_BLOB_CONNECTION_STRING': 'api-storage-azure-blob-connection-string:latest',
            'ANTHROPIC_API_KEY': 'api-anthropic-api-key:latest'})
        env_vars = command.split('ENV_VARS="', 1)[1].split('"', 1)[0]
        for name in secrets:
            self.assertNotIn(f'{name}=', env_vars)
        for secret in secrets.values():
            self.assertIn(secret.removesuffix(':latest'), self.validated_secrets())
        self.assertEqual(len(self.validated_secrets()), len(secrets))
        self.assertIn('gcloud artifacts docker images describe', self.step('image')['run'])
        self.assertIn('@${DIGEST}', self.step('image')['run'])
        self.assertNotIn('|| true', self.step('image')['run'])

    def deploy_env_vars(self, env):
        """Run the deploy step with a fake gcloud; return the parsed `--set-env-vars` mapping."""
        script = ('for arg in "$@"; do\n'
                  '  if [ "$prev" = --set-env-vars ]; then printf %s "$arg" > "$CAPTURE"; fi\n'
                  '  prev="$arg"\n'
                  'done\n')
        with tempfile.TemporaryDirectory() as tmp:
            capture = Path(tmp) / 'env-vars'
            base = {'IMAGE_URI': 'image@sha256:x', 'GCP_PROJECT_ID': 'project', 'GCP_REGION': 'region',
                    'CLOUD_RUN_SERVICE': 'svc', 'CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT': '',
                    'API_STORAGE_PROVIDER': '', 'API_AI_EXTRACTION_ENABLED': '',
                    'API_AI_EXTRACTION_MODEL': '', 'API_CLERK_ISSUER': '',
                    'API_CLERK_AUTHORIZED_PARTIES': '', 'CAPTURE': str(capture)}
            result, _ = self.run_step('deploy', {**base, **env}, {'gcloud': script})
            raw = capture.read_text() if capture.exists() else None
        if result.returncode != 0:
            return result, None
        self.assertTrue(raw.startswith('^|^'), raw)
        return result, dict(item.split('=', 1) for item in raw.removeprefix('^|^').split('|'))

    def test_deploy_passes_clerk_settings_as_plain_env(self):
        parties = '["https://app.example.com","https://my-app.vercel.app"]'
        result, env_vars = self.deploy_env_vars({
            'API_CLERK_ISSUER': 'https://clerk.example.com', 'API_CLERK_AUTHORIZED_PARTIES': parties})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(env_vars['CLERK_ISSUER'], 'https://clerk.example.com')
        self.assertEqual(env_vars['CLERK_AUTHORIZED_PARTIES'], parties)
        self.assertEqual(env_vars['ENVIRONMENT'], 'Production')
        self.assertEqual(env_vars['STORAGE_PROVIDER'], 'Local')
        self.assertFalse(any(name.startswith('JWT_') for name in env_vars))

        result, env_vars = self.deploy_env_vars({'API_CLERK_ISSUER': 'https://clerk.example.com'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('CLERK_AUTHORIZED_PARTIES', env_vars)  # app default applies

        result, _ = self.deploy_env_vars({'API_CLERK_ISSUER': 'https://clerk.example.com|EVIL=1'})
        self.assertNotEqual(result.returncode, 0)

        workflow_env = self.deploy['jobs']['deploy']['env']
        self.assertEqual(workflow_env['API_CLERK_ISSUER'], '${{ vars.API_CLERK_ISSUER }}')
        self.assertEqual(workflow_env['API_CLERK_AUTHORIZED_PARTIES'], '${{ vars.API_CLERK_AUTHORIZED_PARTIES }}')


if __name__ == '__main__':
    unittest.main()
