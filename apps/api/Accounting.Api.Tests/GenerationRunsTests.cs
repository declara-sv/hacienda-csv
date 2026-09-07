using System.Net;
using System.Net.Http.Json;
using Accounting.Api.Domain.Enums;
using Accounting.Api.Features.Generation;
using Accounting.Api.Tests.Infrastructure;

namespace Accounting.Api.Tests;

[Collection("api")]
public sealed class GenerationRunsTests(PostgresFixture fixture)
{
    private static string RunsUrl(Guid clientId, Guid periodId) => $"/api/clients/{clientId}/periods/{periodId}/runs";

    [Fact]
    public async Task Create_run_without_uploads_returns_400()
    {
        var client = await fixture.Factory.RegisterAndLoginAsync();
        var clientId = await client.CreateClientAsync();
        var periodId = await client.CreatePeriodAsync(clientId);

        var response = await client.PostAsync(RunsUrl(clientId, periodId), content: null);

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [Fact]
    public async Task Create_run_snapshots_files_and_assigns_version()
    {
        var client = await fixture.Factory.RegisterAndLoginAsync();
        var clientId = await client.CreateClientAsync();
        var periodId = await client.CreatePeriodAsync(clientId);
        await client.UploadFileAsync(clientId, periodId, "a.pdf");
        await client.UploadFileAsync(clientId, periodId, "b.pdf");

        var response = await client.PostAsync(RunsUrl(clientId, periodId), content: null);

        Assert.Equal(HttpStatusCode.Accepted, response.StatusCode);
        var run = await response.ReadAsAsync<GenerationRunDto>();
        Assert.Equal(1, run.Version);
        Assert.Equal(GenerationRunStatus.Pending, run.Status);
        Assert.Equal(2, run.Files.Count);
        Assert.All(run.Files, f => Assert.Equal(GenerationRunFileStatus.Pending, f.Status));
        Assert.Empty(run.Artifacts);
    }

    [Fact]
    public async Task Create_run_while_active_returns_409_and_concurrent_creates_yield_one_202()
    {
        var client = await fixture.Factory.RegisterAndLoginAsync();
        var clientId = await client.CreateClientAsync();
        var periodId = await client.CreatePeriodAsync(clientId);
        await client.UploadFileAsync(clientId, periodId);

        var first = await client.PostAsync(RunsUrl(clientId, periodId), content: null);
        var second = await client.PostAsync(RunsUrl(clientId, periodId), content: null);
        Assert.Equal(HttpStatusCode.Accepted, first.StatusCode);
        Assert.Equal(HttpStatusCode.Conflict, second.StatusCode);

        var other = await fixture.Factory.RegisterAndLoginAsync();
        var otherClientId = await other.CreateClientAsync();
        var otherPeriodId = await other.CreatePeriodAsync(otherClientId);
        await other.UploadFileAsync(otherClientId, otherPeriodId);

        var results = await Task.WhenAll(
            other.PostAsync(RunsUrl(otherClientId, otherPeriodId), content: null),
            other.PostAsync(RunsUrl(otherClientId, otherPeriodId), content: null));

        Assert.Equal(1, results.Count(r => r.StatusCode == HttpStatusCode.Accepted));
        Assert.Equal(1, results.Count(r => r.StatusCode == HttpStatusCode.Conflict));
    }

    [Fact]
    public async Task List_and_get_return_runs_newest_version_first()
    {
        var client = await fixture.Factory.RegisterAndLoginAsync();
        var clientId = await client.CreateClientAsync();
        var periodId = await client.CreatePeriodAsync(clientId);
        await client.UploadFileAsync(clientId, periodId);
        var created = await (await client.PostAsync(RunsUrl(clientId, periodId), content: null)).ReadAsAsync<GenerationRunDto>();

        var list = await (await client.GetAsync(RunsUrl(clientId, periodId))).ReadAsAsync<List<GenerationRunDto>>();
        var single = await (await client.GetAsync($"{RunsUrl(clientId, periodId)}/{created.Id}")).ReadAsAsync<GenerationRunDto>();

        Assert.Single(list);
        Assert.Equal(created.Id, list[0].Id);
        Assert.Equal(created.Id, single.Id);
    }

    [Fact]
    public async Task Status_serializes_as_string()
    {
        var client = await fixture.Factory.RegisterAndLoginAsync();
        var clientId = await client.CreateClientAsync();
        var periodId = await client.CreatePeriodAsync(clientId);
        await client.UploadFileAsync(clientId, periodId);

        var raw = await (await client.PostAsync(RunsUrl(clientId, periodId), content: null)).Content.ReadAsStringAsync();

        Assert.Contains("\"status\":\"Pending\"", raw);
    }

    [Fact]
    public async Task Other_user_gets_404_on_create_list_and_get()
    {
        var owner = await fixture.Factory.RegisterAndLoginAsync();
        var clientId = await owner.CreateClientAsync();
        var periodId = await owner.CreatePeriodAsync(clientId);
        await owner.UploadFileAsync(clientId, periodId);
        var created = await (await owner.PostAsync(RunsUrl(clientId, periodId), content: null)).ReadAsAsync<GenerationRunDto>();

        var intruder = await fixture.Factory.RegisterAndLoginAsync();

        Assert.Equal(HttpStatusCode.NotFound, (await intruder.PostAsync(RunsUrl(clientId, periodId), content: null)).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await intruder.GetAsync(RunsUrl(clientId, periodId))).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await intruder.GetAsync($"{RunsUrl(clientId, periodId)}/{created.Id}")).StatusCode);
    }
}
