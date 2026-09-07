using System.Net;
using Accounting.Api.Data;
using Accounting.Api.Domain.Enums;
using Accounting.Api.Features.Generation;
using Accounting.Api.Features.Uploads;
using Accounting.Api.Storage;
using Accounting.Api.Tests.Infrastructure;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace Accounting.Api.Tests;

[Collection("api")]
public sealed class GenerationProcessorTests(PostgresFixture fixture)
{
    private static string RunsUrl(Guid clientId, Guid periodId) => $"/api/clients/{clientId}/periods/{periodId}/runs";

    private async Task<(HttpClient Client, Guid ClientId, Guid PeriodId)> SetupPeriodWithFilesAsync(params string[] fileNames)
    {
        var client = await fixture.Factory.RegisterAndLoginAsync();
        var clientId = await client.CreateClientAsync();
        var periodId = await client.CreatePeriodAsync(clientId, 2026, 1);
        foreach (var name in fileNames)
        {
            (await client.UploadFileAsync(clientId, periodId, name)).EnsureSuccessStatusCode();
        }
        return (client, clientId, periodId);
    }

    private async Task<GenerationRunDto> CreateRunAsync(HttpClient client, Guid clientId, Guid periodId)
    {
        var response = await client.PostAsync(RunsUrl(clientId, periodId), content: null);
        Assert.Equal(HttpStatusCode.Accepted, response.StatusCode);
        return await response.ReadAsAsync<GenerationRunDto>();
    }

    [Fact]
    public async Task Concurrent_claims_return_exactly_one_run()
    {
        var (client, clientId, periodId) = await SetupPeriodWithFilesAsync("a.pdf");
        var run = await CreateRunAsync(client, clientId, periodId);

        await using var scopeA = fixture.Factory.CreateScope();
        await using var scopeB = fixture.Factory.CreateScope();
        var processorA = scopeA.ServiceProvider.GetRequiredService<GenerationRunProcessor>();
        var processorB = scopeB.ServiceProvider.GetRequiredService<GenerationRunProcessor>();

        // Drain any other pending runs left by earlier tests so only this one is claimable.
        await using (var drain = fixture.Factory.CreateScope())
        {
            var db = drain.ServiceProvider.GetRequiredService<AppDbContext>();
            await db.GenerationRuns
                .Where(r => r.Status == GenerationRunStatus.Pending && r.Id != run.Id)
                .ExecuteUpdateAsync(s => s.SetProperty(r => r.Status, GenerationRunStatus.Failed));
        }

        var claims = await Task.WhenAll(
            processorA.TryClaimAsync(CancellationToken.None),
            processorB.TryClaimAsync(CancellationToken.None));

        Assert.Equal(1, claims.Count(id => id == run.Id));
        Assert.Equal(1, claims.Count(id => id is null));
    }

    [Fact]
    public async Task Stuck_running_run_is_failed_by_recovery()
    {
        var (client, clientId, periodId) = await SetupPeriodWithFilesAsync("a.pdf");
        var run = await CreateRunAsync(client, clientId, periodId);

        await using (var scope = fixture.Factory.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
            await db.GenerationRuns.Where(r => r.Id == run.Id).ExecuteUpdateAsync(s => s
                .SetProperty(r => r.Status, GenerationRunStatus.Running)
                .SetProperty(r => r.StartedAtUtc, DateTime.UtcNow.AddMinutes(-30)));
        }

        await using var work = fixture.Factory.CreateScope();
        var processor = work.ServiceProvider.GetRequiredService<GenerationRunProcessor>();
        var recovered = await processor.RecoverStuckRunsAsync(CancellationToken.None);

        Assert.True(recovered >= 1);
        var after = await (await client.GetAsync($"{RunsUrl(clientId, periodId)}/{run.Id}")).ReadAsAsync<GenerationRunDto>();
        Assert.Equal(GenerationRunStatus.Failed, after.Status);
        Assert.NotNull(after.ErrorMessage);
    }

    [Fact]
    public async Task Processing_two_files_yields_one_artifact_with_two_rows_and_marks_included()
    {
        var (client, clientId, periodId) = await SetupPeriodWithFilesAsync("a.pdf", "b.pdf");
        var run = await CreateRunAsync(client, clientId, periodId);

        await using var scope = fixture.Factory.CreateScope();
        var processor = scope.ServiceProvider.GetRequiredService<GenerationRunProcessor>();
        await processor.ProcessAsync(run.Id, CancellationToken.None);

        var after = await (await client.GetAsync($"{RunsUrl(clientId, periodId)}/{run.Id}")).ReadAsAsync<GenerationRunDto>();
        Assert.Equal(GenerationRunStatus.Completed, after.Status);
        Assert.All(after.Files, f => Assert.Equal(GenerationRunFileStatus.Included, f.Status));
        Assert.Single(after.Artifacts);

        var download = await client.GetAsync($"/api/artifacts/{after.Artifacts[0].Id}/download");
        Assert.Equal(HttpStatusCode.OK, download.StatusCode);
        var csv = await download.Content.ReadAsStringAsync();
        var lines = csv.Split('\n', StringSplitOptions.RemoveEmptyEntries);
        Assert.Equal(3, lines.Length); // header + 2 rows
    }

    [Fact]
    public async Task Missing_storage_object_marks_file_failed_and_run_completes_or_fails_accordingly()
    {
        var (client, clientId, periodId) = await SetupPeriodWithFilesAsync("a.pdf", "b.pdf");
        var run = await CreateRunAsync(client, clientId, periodId);

        await using (var scope = fixture.Factory.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
            var first = await db.Uploads.Where(u => u.FilingPeriodId == periodId).OrderBy(u => u.OriginalFileName).FirstAsync();
            File.Delete(Path.Combine(fixture.Factory.StorageRoot, first.StorageContainer, first.StoragePath));
        }

        await using (var scope = fixture.Factory.CreateScope())
        {
            await scope.ServiceProvider.GetRequiredService<GenerationRunProcessor>().ProcessAsync(run.Id, CancellationToken.None);
        }

        var after = await (await client.GetAsync($"{RunsUrl(clientId, periodId)}/{run.Id}")).ReadAsAsync<GenerationRunDto>();
        Assert.Equal(GenerationRunStatus.Completed, after.Status);
        Assert.Equal(1, after.Files.Count(f => f.Status == GenerationRunFileStatus.Failed));
        Assert.Equal(1, after.Files.Count(f => f.Status == GenerationRunFileStatus.Included));

        // Now a run where every file is missing must fail.
        var (client2, clientId2, periodId2) = await SetupPeriodWithFilesAsync("solo.pdf");
        var run2 = await CreateRunAsync(client2, clientId2, periodId2);
        await using (var scope = fixture.Factory.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
            var only = await db.Uploads.SingleAsync(u => u.FilingPeriodId == periodId2);
            File.Delete(Path.Combine(fixture.Factory.StorageRoot, only.StorageContainer, only.StoragePath));
        }
        await using (var scope = fixture.Factory.CreateScope())
        {
            await scope.ServiceProvider.GetRequiredService<GenerationRunProcessor>().ProcessAsync(run2.Id, CancellationToken.None);
        }
        var after2 = await (await client2.GetAsync($"{RunsUrl(clientId2, periodId2)}/{run2.Id}")).ReadAsAsync<GenerationRunDto>();
        Assert.Equal(GenerationRunStatus.Failed, after2.Status);
    }

    [Fact]
    public async Task Upload_after_completed_run_is_not_included_in_latest_run()
    {
        var (client, clientId, periodId) = await SetupPeriodWithFilesAsync("a.pdf");
        var run = await CreateRunAsync(client, clientId, periodId);
        await using (var scope = fixture.Factory.CreateScope())
        {
            await scope.ServiceProvider.GetRequiredService<GenerationRunProcessor>().ProcessAsync(run.Id, CancellationToken.None);
        }

        (await client.UploadFileAsync(clientId, periodId, "later.pdf")).EnsureSuccessStatusCode();

        var uploads = await (await client.GetAsync($"/api/clients/{clientId}/periods/{periodId}/uploads")).ReadAsAsync<List<UploadDto>>();

        Assert.False(uploads.Single(u => u.OriginalFileName == "later.pdf").IncludedInLatestRun);
        Assert.True(uploads.Single(u => u.OriginalFileName == "a.pdf").IncludedInLatestRun);

        // The first run is Completed, so a second run is allowed and gets the next version.
        var second = await CreateRunAsync(client, clientId, periodId);
        Assert.Equal(2, second.Version);
        Assert.Equal(2, second.Files.Count);
    }

    private sealed class ThrowingFileStorage(IFileStorage inner, string throwOnPathSubstring) : IFileStorage
    {
        public string ProviderName => inner.ProviderName;

        public Task<StoredFileReference> SaveAsync(
            string container,
            string path,
            Stream content,
            string contentType,
            CancellationToken cancellationToken = default)
            => inner.SaveAsync(container, path, content, contentType, cancellationToken);

        public Task<Stream?> OpenReadAsync(StoredFileReference file, CancellationToken cancellationToken = default)
        {
            if (file.Path.Contains(throwOnPathSubstring, StringComparison.Ordinal))
            {
                throw new IOException("Fallo simulado de almacenamiento.");
            }

            return inner.OpenReadAsync(file, cancellationToken);
        }

        public Task DeleteAsync(StoredFileReference file, CancellationToken cancellationToken = default)
            => inner.DeleteAsync(file, cancellationToken);
    }

    [Fact]
    public async Task Storage_exception_on_one_file_marks_it_failed_and_run_completes()
    {
        var (client, clientId, periodId) = await SetupPeriodWithFilesAsync("a.pdf", "b.pdf");
        var run = await CreateRunAsync(client, clientId, periodId);

        await using var scope = fixture.Factory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        var failing = await db.Uploads.SingleAsync(u => u.FilingPeriodId == periodId && u.OriginalFileName == "b.pdf");

        var innerStorage = scope.ServiceProvider.GetRequiredService<IFileStorage>();
        var throwingStorage = new ThrowingFileStorage(innerStorage, failing.StoragePath);

        var processor = new GenerationRunProcessor(
            db,
            throwingStorage,
            scope.ServiceProvider.GetRequiredService<ICsvGenerator>(),
            scope.ServiceProvider.GetRequiredService<IOptions<StorageOptions>>(),
            scope.ServiceProvider.GetRequiredService<IOptions<GenerationOptions>>(),
            scope.ServiceProvider.GetRequiredService<ILogger<GenerationRunProcessor>>());

        await processor.ProcessAsync(run.Id, CancellationToken.None);

        var after = await (await client.GetAsync($"{RunsUrl(clientId, periodId)}/{run.Id}")).ReadAsAsync<GenerationRunDto>();
        Assert.Equal(GenerationRunStatus.Completed, after.Status);

        var failed = Assert.Single(after.Files, f => f.Status == GenerationRunFileStatus.Failed);
        Assert.Contains("Error al leer", failed.ErrorMessage);
        Assert.Single(after.Files, f => f.Status == GenerationRunFileStatus.Included);
        Assert.Single(after.Artifacts);
    }

    [Fact]
    public async Task Other_user_cannot_download_artifact()
    {
        var (client, clientId, periodId) = await SetupPeriodWithFilesAsync("a.pdf");
        var run = await CreateRunAsync(client, clientId, periodId);
        await using (var scope = fixture.Factory.CreateScope())
        {
            await scope.ServiceProvider.GetRequiredService<GenerationRunProcessor>().ProcessAsync(run.Id, CancellationToken.None);
        }
        var after = await (await client.GetAsync($"{RunsUrl(clientId, periodId)}/{run.Id}")).ReadAsAsync<GenerationRunDto>();

        var intruder = await fixture.Factory.RegisterAndLoginAsync();
        var download = await intruder.GetAsync($"/api/artifacts/{after.Artifacts[0].Id}/download");

        Assert.Equal(HttpStatusCode.NotFound, download.StatusCode);
    }
}
