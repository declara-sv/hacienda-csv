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
}
