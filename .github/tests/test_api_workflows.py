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

    def test_ci_covers_branches_and_runs_strict_build_and_tests(self):
        self.assertIn('on', self.ci, 'CI workflow must exist')
        self.assertEqual(self.ci['on']['push']['branches'], ['**'])
        for event in ('push', 'pull_request'):
            for path in ('apps/api/**', 'global.json', '.github/workflows/**', '.github/tests/**'):
                self.assertIn(path, self.ci['on'][event]['paths'])
        self.assertEqual(self.ci['permissions'], {'contents': 'read'})
        commands = '\n'.join(s.get('run', '') for s in self.ci['jobs']['test']['steps'])
        for command in ('dotnet restore apps/api/Accounting.slnx',
                        'dotnet build apps/api/Accounting.slnx --no-restore -warnaserror',
                        'dotnet test apps/api/Accounting.Api.Tests --no-build',
                        'python -m unittest discover -s .github/tests -v'):
            self.assertIn(command, commands)

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
            'GCP_PROJECT_ID', 'GCP_REGION', 'GAR_REPOSITORY', 'CLOUD_RUN_SERVICE',
            'SEC_GCP_WORKLOAD_IDENTITY_PROVIDER', 'SEC_GCP_SERVICE_ACCOUNT')}
        for key in env:
            result, _ = self.run_step('validate', {**env, key: ''})
            self.assertNotEqual(result.returncode, 0, key)
        result, _ = self.run_step('validate', env)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = (WORKFLOWS / 'deploy-api.yml').read_text()
        self.assertEqual(text.count('secrets.API_CONNECTION_STRING_POSTGRES'), 1)
        self.assertNotIn('secrets.API_JWT_SIGNING_KEY', text)
        self.assertNotIn('secrets.API_STORAGE_AZURE_BLOB_CONNECTION_STRING', text)

    def test_manual_dispatch_skips_build_and_migrations(self):
        steps = self.steps()
        for id in ('docker-auth', 'builder', 'build', 'dotnet', 'bundle', 'migrate'):
            self.assertEqual(self.step(id)['if'], "github.event_name == 'push'", id)
        self.assertLess(steps.index(self.step('migrate')), steps.index(self.step('deploy')))
        for id in ('migrate', 'deploy'):
            self.assertNotIn('continue-on-error', self.step(id))
        self.assertNotIn('if', self.step('deploy'))  # default success() gate
        self.assertIn('--self-contained -r linux-x64 -o efbundle', self.step('bundle')['run'])
        self.assertIn('./efbundle --connection "$CONNECTION_STRING"', self.step('migrate')['run'])
        result, _ = self.run_step('migrate', {'CONNECTION_STRING': ''})
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

    def test_bundle_failure_is_not_swallowed_and_connection_is_one_argument(self):
        connection = 'Host=test;Password=spaces ; $literal and "quotes"'
        script = '[[ "$#" == 2 && "$1" == --connection && "$2" == "$CONNECTION_STRING" ]] || exit 90\nexit 42'
        result, _ = self.run_step('migrate', {'CONNECTION_STRING': connection}, {'efbundle': script})
        self.assertEqual(result.returncode, 42, result.stderr)
        self.assertNotIn(connection, result.stdout + result.stderr)

    def test_deploy_uses_digest_and_secret_manager_not_plaintext(self):
        command = self.step('deploy')['run']
        self.assertIn('--image "$IMAGE_URI"', command)
        self.assertIn('Features__EnableSwagger=false', command)
        for env, secret in (
            ('ConnectionStrings__Postgres', 'api-connection-string-postgres'),
            ('Jwt__SigningKey', 'api-jwt-signing-key'),
            ('Storage__AzureBlobConnectionString', 'api-storage-azure-blob-connection-string')):
            self.assertIn(f'{env}={secret}:latest', command)
            self.assertNotIn(f'--set-env-vars "{env}=', command)
        self.assertIn('--set-secrets', command)
        self.assertIn('gcloud artifacts docker images describe', self.step('image')['run'])
        self.assertIn('@${DIGEST}', self.step('image')['run'])
        self.assertNotIn('|| true', self.step('image')['run'])


if __name__ == '__main__':
    unittest.main()
