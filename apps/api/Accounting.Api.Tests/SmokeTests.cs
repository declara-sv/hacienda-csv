using System.Net;
using Accounting.Api.Tests.Infrastructure;

namespace Accounting.Api.Tests;

[Collection("api")]
public sealed class SmokeTests(PostgresFixture fixture)
{
    [Fact]
    public async Task Health_returns_ok()
    {
        var client = fixture.Factory.CreateClient();
        var response = await client.GetAsync("/health");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task Register_login_and_create_period_work()
    {
        var client = await fixture.Factory.RegisterAndLoginAsync();
        var clientId = await client.CreateClientAsync();
        var periodId = await client.CreatePeriodAsync(clientId);

        Assert.NotEqual(Guid.Empty, clientId);
        Assert.NotEqual(Guid.Empty, periodId);
    }

    [Fact]
    public async Task Unknown_route_under_api_returns_problem_details_shape_for_404()
    {
        var client = await fixture.Factory.RegisterAndLoginAsync();
        var response = await client.GetAsync($"/api/clients/{Guid.NewGuid()}");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal("application/problem+json", response.Content.Headers.ContentType?.MediaType);
    }

    [Fact]
    public async Task Startup_does_not_run_migrations()
    {
        var source = await File.ReadAllTextAsync(Path.Combine(FindRepoRoot(), "apps", "api", "Accounting.Api", "Program.cs"));
        Assert.DoesNotContain("Database.Migrate()", source);
    }

    private static string FindRepoRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && !File.Exists(Path.Combine(dir.FullName, "README.md")))
        {
            dir = dir.Parent;
        }
        return dir?.FullName ?? throw new InvalidOperationException("No se encontró la raíz del repo.");
    }
}
