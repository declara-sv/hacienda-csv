using Accounting.Api.Data;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Accounting.Api.Tests.Infrastructure;

public sealed class ApiFactory(string connectionString) : WebApplicationFactory<Program>
{
    public string StorageRoot { get; } = Path.Combine(Path.GetTempPath(), "accounting-tests", Guid.NewGuid().ToString("N"));

    // Program.cs reads ConnectionStrings:Postgres and Jwt:* directly off builder.Configuration
    // *before* builder.Build() runs. WebApplicationFactory only gets a chance to inject
    // ConfigureAppConfiguration/ConfigureTestServices once Build() is already underway (too late
    // for those eager reads), so the values below must land via environment variables, which
    // WebApplication.CreateBuilder(args) picks up at the very start of Program.cs. This must run
    // before the host is created, hence overriding CreateHostBuilder rather than ConfigureWebHost.
    protected override IHostBuilder CreateHostBuilder()
    {
        Environment.SetEnvironmentVariable("ConnectionStrings__Postgres", connectionString);
        Environment.SetEnvironmentVariable("Storage__Provider", "Local");
        Environment.SetEnvironmentVariable("Storage__LocalRootPath", StorageRoot);
        Environment.SetEnvironmentVariable("Jwt__SigningKey", "test-signing-key-for-integration-tests-0123456789");
        Environment.SetEnvironmentVariable("Jwt__AccessTokenMinutes", "20");
        Environment.SetEnvironmentVariable("Generation__PollIntervalSeconds", "1");
        Environment.SetEnvironmentVariable("Generation__RunTimeoutMinutes", "10");
        return base.CreateHostBuilder()!;
    }

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("Development");

        // Values are supplied via the environment variables set in CreateHostBuilder above, since
        // Program.cs reads them before this callback ever runs. No ConfigureAppConfiguration here
        // to avoid two sources of truth for the same keys.
        builder.ConfigureTestServices(services =>
        {
            // Tests drive processing explicitly; no background worker from the app namespace may run.
            var hosted = services
                .Where(d => d.ServiceType == typeof(IHostedService)
                            && d.ImplementationType?.Namespace?.StartsWith("Accounting.Api", StringComparison.Ordinal) == true)
                .ToList();
            foreach (var descriptor in hosted)
            {
                services.Remove(descriptor);
            }
        });
    }

    public async Task MigrateAsync()
    {
        using var scope = Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        await db.Database.MigrateAsync();
    }

    public AsyncServiceScope CreateScope() => Services.CreateAsyncScope();

    protected override void Dispose(bool disposing)
    {
        base.Dispose(disposing);
        if (disposing && Directory.Exists(StorageRoot))
        {
            Directory.Delete(StorageRoot, recursive: true);
        }
    }
}
