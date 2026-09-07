using Accounting.Api.Data;
using Accounting.Api.Tests.Infrastructure;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Accounting.Api.Tests;

[Collection("api")]
public sealed class MigrationTests(PostgresFixture fixture)
{
    [Fact]
    public async Task Model_has_no_pending_changes_and_generation_tables_exist()
    {
        await using var scope = fixture.Factory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();

        Assert.False(db.Database.HasPendingModelChanges());

        var tables = await db.Database
            .SqlQueryRaw<string>("SELECT table_name AS \"Value\" FROM information_schema.tables WHERE table_schema = 'public'")
            .ToListAsync();

        Assert.Contains("generation_runs", tables);
        Assert.Contains("generation_run_files", tables);
        Assert.DoesNotContain("parse_jobs", tables);
    }

    [Fact]
    public async Task Active_run_partial_unique_index_exists()
    {
        await using var scope = fixture.Factory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();

        var definitions = await db.Database
            .SqlQueryRaw<string>("SELECT indexdef AS \"Value\" FROM pg_indexes WHERE tablename = 'generation_runs'")
            .ToListAsync();

        Assert.Contains(definitions, d => d.Contains("UNIQUE", StringComparison.Ordinal)
                                          && d.Contains("WHERE", StringComparison.Ordinal)
                                          && d.Contains("Pending", StringComparison.Ordinal));
    }
}
