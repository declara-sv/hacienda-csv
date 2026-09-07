# Generation Runs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace per-file `ParseJob` processing with period-level, versioned generation runs that consume every upload in a filing period and produce one consolidated CSV, with an atomically claimed worker and an integration test suite.

**Architecture:** Uploads become plain source documents (list, create, delete). A `GenerationRun` snapshots the period's uploads into `GenerationRunFile` rows at creation, and a `GenerationRunProcessor` claims runs with `FOR UPDATE SKIP LOCKED`, recovers stuck runs by timeout, and writes `OutputArtifact` rows through an `ICsvGenerator` seam whose only implementation is a placeholder. New code lives in `Features/Uploads` and `Features/Generation`; the old controller, DTOs, worker, and `ParseJob` are deleted.

**Tech Stack:** .NET 10, ASP.NET Core MVC controllers, EF Core 10.0.3 + Npgsql 10.0.0, PostgreSQL 16, xUnit 2.9.2, Microsoft.AspNetCore.Mvc.Testing 10.0.11, Testcontainers.PostgreSql 4.14.0, dotnet-ef 10.0.11 (local tool).

**Spec:** `docs/superpowers/specs/2026-09-06-generation-runs-design.md`

## Global Constraints

- Repo root: `/Users/kelvinrojas/.t3/worktrees/hacienda-csv/t3code-597d3c9c`. API project: `apps/api/Accounting.Api`. Solution: `apps/api/Accounting.slnx`. All `dotnet` commands below run from the repo root unless stated.
- Table names are snake_case via `ToTable`. Column names are PascalCase and must be double-quoted in raw SQL, e.g. `"Status"`, `"CreatedAtUtc"`.
- Timestamps are `DateTime` with `Kind = Utc`, assigned with `DateTime.UtcNow`. Postgres column type is `timestamp with time zone`.
- Enums are stored as strings via `HasConversion` with `HasMaxLength(20)`.
- Ownership is resolved with `dbContext.FindOwnedFilingPeriodAsync(clientId, filingPeriodId, userId, ct)` from `Data/OwnershipQueries.cs`. Not-owned or missing resources return 404, never 403.
- User-facing messages are Spanish, matching existing code (`"El archivo está vacío."`).
- Controllers use primary constructors, `[ApiController] [Authorize]`, and `[ProducesResponseType]` attributes, as in the existing controllers.
- Existing controllers for auth, clients, client configs, and filing periods must not be modified.
- Every task ends with `dotnet build apps/api/Accounting.slnx` succeeding with zero errors and the test suite green (`dotnet test apps/api/Accounting.slnx`). Docker must be running for tests.
- Commit after each task with a conventional commit message and the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

---

## File map

Created:

- `apps/api/.config/dotnet-tools.json` — local tool manifest with dotnet-ef
- `apps/api/Accounting.Api.Tests/Accounting.Api.Tests.csproj`
- `apps/api/Accounting.Api.Tests/Infrastructure/PostgresFixture.cs` — one Postgres container per test collection
- `apps/api/Accounting.Api.Tests/Infrastructure/ApiFactory.cs` — `WebApplicationFactory<Program>` with test config, migrations, worker disabled
- `apps/api/Accounting.Api.Tests/Infrastructure/ApiCollection.cs` — xUnit collection definition
- `apps/api/Accounting.Api.Tests/Infrastructure/ApiClientExtensions.cs` — register/login/create client/create period/upload helpers
- `apps/api/Accounting.Api.Tests/SmokeTests.cs`
- `apps/api/Accounting.Api.Tests/MigrationTests.cs`
- `apps/api/Accounting.Api.Tests/UploadsTests.cs`
- `apps/api/Accounting.Api.Tests/GenerationRunsTests.cs`
- `apps/api/Accounting.Api.Tests/GenerationProcessorTests.cs`
- `apps/api/Accounting.Api/Domain/Entities/GenerationRun.cs`
- `apps/api/Accounting.Api/Domain/Entities/GenerationRunFile.cs`
- `apps/api/Accounting.Api/Domain/Enums/GenerationRunStatus.cs`
- `apps/api/Accounting.Api/Domain/Enums/GenerationRunFileStatus.cs`
- `apps/api/Accounting.Api/Migrations/<timestamp>_GenerationRuns.cs` (+ Designer, generated)
- `apps/api/Accounting.Api/Features/Uploads/UploadDtos.cs`
- `apps/api/Accounting.Api/Features/Uploads/UploadsService.cs`
- `apps/api/Accounting.Api/Features/Uploads/UploadsController.cs`
- `apps/api/Accounting.Api/Features/Generation/GenerationRunDtos.cs`
- `apps/api/Accounting.Api/Features/Generation/GenerationRunsService.cs`
- `apps/api/Accounting.Api/Features/Generation/GenerationRunsController.cs`
- `apps/api/Accounting.Api/Features/Generation/GenerationOptions.cs`
- `apps/api/Accounting.Api/Features/Generation/ICsvGenerator.cs`
- `apps/api/Accounting.Api/Features/Generation/PlaceholderCsvGenerator.cs`
- `apps/api/Accounting.Api/Features/Generation/GenerationRunProcessor.cs`
- `apps/api/Accounting.Api/Features/Generation/GenerationWorker.cs`

Modified:

- `apps/api/Accounting.slnx` — add test project
- `apps/api/Accounting.Api/Program.cs` — partial class, JSON enum converter, exception handler, generation DI, remove startup migrate
- `apps/api/Accounting.Api/Data/AppDbContext.cs` — new entities, remove ParseJob, re-point OutputArtifact
- `apps/api/Accounting.Api/Domain/Entities/Upload.cs`, `FilingPeriod.cs`, `OutputArtifact.cs`
- `apps/api/Accounting.Api/Storage/IFileStorage.cs`, `LocalFileStorage.cs`, `AzureBlobFileStorage.cs` — add `DeleteAsync`
- `apps/api/Accounting.Api/Migrations/AppDbContextModelSnapshot.cs` (generated)
- `README.md` — migrations are manual now

Deleted:

- `apps/api/Accounting.Api/Controllers/UploadsController.cs`
- `apps/api/Accounting.Api/DTOs/Uploads/UploadDtos.cs`
- `apps/api/Accounting.Api/Workers/ParsePipelineWorker.cs`
- `apps/api/Accounting.Api/Domain/Entities/ParseJob.cs`
- `apps/api/Accounting.Api/Domain/Enums/ParseJobStatus.cs`

---

### Task 1: Test project and Postgres test harness

**Files:**
- Create: `apps/api/.config/dotnet-tools.json`
- Create: `apps/api/Accounting.Api.Tests/Accounting.Api.Tests.csproj`
- Create: `apps/api/Accounting.Api.Tests/Infrastructure/PostgresFixture.cs`
- Create: `apps/api/Accounting.Api.Tests/Infrastructure/ApiFactory.cs`
- Create: `apps/api/Accounting.Api.Tests/Infrastructure/ApiCollection.cs`
- Create: `apps/api/Accounting.Api.Tests/Infrastructure/ApiClientExtensions.cs`
- Create: `apps/api/Accounting.Api.Tests/SmokeTests.cs`
- Modify: `apps/api/Accounting.slnx`
- Modify: `apps/api/Accounting.Api/Program.cs` (append one line)

**Interfaces:**
- Produces: `[Collection("api")]` attribute for every test class; `ApiFactory` with `HttpClient CreateClient()`, `IServiceProvider Services`, `string StorageRoot`; extension methods `RegisterAndLoginAsync`, `CreateClientAsync`, `CreatePeriodAsync`, `UploadFileAsync` on `HttpClient`; `IdResponse` record.

- [ ] **Step 1: Install dotnet-ef as a local tool**

```bash
cd apps/api && dotnet new tool-manifest && dotnet tool install dotnet-ef --version 10.0.11 && cd ../..
```

Expected: `apps/api/.config/dotnet-tools.json` exists and `dotnet ef --version` prints `10.0.11` when run from `apps/api`.

- [ ] **Step 2: Create the test project**

Create `apps/api/Accounting.Api.Tests/Accounting.Api.Tests.csproj`:

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <IsPackable>false</IsPackable>
    <IsTestProject>true</IsTestProject>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="Microsoft.AspNetCore.Mvc.Testing" Version="10.0.11" />
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="18.8.1" />
    <PackageReference Include="Testcontainers.PostgreSql" Version="4.14.0" />
    <PackageReference Include="xunit" Version="2.9.2" />
    <PackageReference Include="xunit.runner.visualstudio" Version="3.1.5">
      <PrivateAssets>all</PrivateAssets>
      <IncludeAssets>runtime; build; native; contentfiles; analyzers; buildtransitive</IncludeAssets>
    </PackageReference>
  </ItemGroup>

  <ItemGroup>
    <ProjectReference Include="../Accounting.Api/Accounting.Api.csproj" />
  </ItemGroup>

  <ItemGroup>
    <Using Include="Xunit" />
  </ItemGroup>
</Project>
```

Replace `apps/api/Accounting.slnx` with:

```xml
<Solution>
  <Project Path="Accounting.Api/Accounting.Api.csproj" />
  <Project Path="Accounting.Api.Tests/Accounting.Api.Tests.csproj" />
</Solution>
```

- [ ] **Step 3: Make `Program` visible to the test host**

Append to the end of `apps/api/Accounting.Api/Program.cs`, after `app.Run();`:

```csharp

public partial class Program;
```

- [ ] **Step 4: Write the Postgres fixture**

Create `apps/api/Accounting.Api.Tests/Infrastructure/PostgresFixture.cs`:

```csharp
using Testcontainers.PostgreSql;

namespace Accounting.Api.Tests.Infrastructure;

public sealed class PostgresFixture : IAsyncLifetime
{
    private readonly PostgreSqlContainer _container = new PostgreSqlBuilder()
        .WithImage("postgres:16-alpine")
        .WithDatabase("accounting_test")
        .WithUsername("postgres")
        .WithPassword("postgres")
        .Build();

    public string ConnectionString => _container.GetConnectionString();

    public ApiFactory Factory { get; private set; } = null!;

    public async Task InitializeAsync()
    {
        await _container.StartAsync();
        Factory = new ApiFactory(ConnectionString);
        await Factory.MigrateAsync();
    }

    public async Task DisposeAsync()
    {
        await Factory.DisposeAsync();
        await _container.DisposeAsync();
    }
}
```

- [ ] **Step 5: Write the API factory**

Create `apps/api/Accounting.Api.Tests/Infrastructure/ApiFactory.cs`:

```csharp
using Accounting.Api.Data;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Accounting.Api.Tests.Infrastructure;

public sealed class ApiFactory(string connectionString) : WebApplicationFactory<Program>
{
    public string StorageRoot { get; } = Path.Combine(Path.GetTempPath(), "accounting-tests", Guid.NewGuid().ToString("N"));

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("Development");

        builder.ConfigureAppConfiguration((_, config) =>
        {
            config.AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ConnectionStrings:Postgres"] = connectionString,
                ["Storage:Provider"] = "Local",
                ["Storage:LocalRootPath"] = StorageRoot,
                ["Jwt:SigningKey"] = "test-signing-key-for-integration-tests-0123456789",
                ["Jwt:AccessTokenMinutes"] = "20",
                ["Generation:PollIntervalSeconds"] = "1",
                ["Generation:RunTimeoutMinutes"] = "10",
            });
        });

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
```

- [ ] **Step 6: Define the collection and client helpers**

Create `apps/api/Accounting.Api.Tests/Infrastructure/ApiCollection.cs`:

```csharp
namespace Accounting.Api.Tests.Infrastructure;

[CollectionDefinition("api")]
public sealed class ApiCollection : ICollectionFixture<PostgresFixture>;
```

Create `apps/api/Accounting.Api.Tests/Infrastructure/ApiClientExtensions.cs`:

```csharp
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Accounting.Api.Tests.Infrastructure;

public sealed record IdResponse(Guid Id);

public sealed record AuthResponse(string AccessToken, string RefreshToken);

public static class ApiClientExtensions
{
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web)
    {
        Converters = { new JsonStringEnumConverter() },
    };

    public static async Task<HttpClient> RegisterAndLoginAsync(this ApiFactory factory, string? email = null)
    {
        var client = factory.CreateClient();
        email ??= $"user-{Guid.NewGuid():N}@test.local";
        var register = await client.PostAsJsonAsync("/api/auth/register", new
        {
            email,
            password = "Password123!",
            fullName = "Test User",
        }, Json);
        register.EnsureSuccessStatusCode();

        var auth = await register.Content.ReadFromJsonAsync<AuthResponse>(Json)
                   ?? throw new InvalidOperationException("Sin respuesta de registro.");
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", auth.AccessToken);
        return client;
    }

    public static async Task<Guid> CreateClientAsync(this HttpClient client, string name = "Cliente Test")
    {
        var response = await client.PostAsJsonAsync("/api/clients", new
        {
            name,
            taxId = $"NIT-{Random.Shared.Next(100000, 999999)}",
            notes = (string?)null,
        }, Json);
        response.EnsureSuccessStatusCode();
        var body = await response.Content.ReadFromJsonAsync<IdResponse>(Json);
        return body!.Id;
    }

    public static async Task<Guid> CreatePeriodAsync(this HttpClient client, Guid clientId, int year = 2026, int month = 1)
    {
        var response = await client.PostAsJsonAsync($"/api/clients/{clientId}/periods", new { year, month }, Json);
        response.EnsureSuccessStatusCode();
        var body = await response.Content.ReadFromJsonAsync<IdResponse>(Json);
        return body!.Id;
    }

    public static async Task<HttpResponseMessage> UploadFileAsync(
        this HttpClient client,
        Guid clientId,
        Guid periodId,
        string fileName = "factura.pdf",
        string sourceFileKind = "PDF",
        byte[]? content = null)
    {
        content ??= "%PDF-1.4 test"u8.ToArray();
        using var form = new MultipartFormDataContent();
        var file = new ByteArrayContent(content);
        file.Headers.ContentType = new MediaTypeHeaderValue(sourceFileKind == "PDF" ? "application/pdf" : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
        form.Add(file, "file", fileName);
        form.Add(new StringContent(sourceFileKind), "sourceFileKind");
        return await client.PostAsync($"/api/clients/{clientId}/periods/{periodId}/uploads", form);
    }

    public static async Task<T> ReadAsAsync<T>(this HttpResponseMessage response)
    {
        var body = await response.Content.ReadFromJsonAsync<T>(Json);
        return body ?? throw new InvalidOperationException($"Cuerpo vacío para {typeof(T).Name}.");
    }
}
```

- [ ] **Step 7: Write the smoke tests**

Create `apps/api/Accounting.Api.Tests/SmokeTests.cs`:

```csharp
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
```

- [ ] **Step 8: Run the tests**

Run: `dotnet test apps/api/Accounting.slnx`
Expected: 2 passed. If Docker is not running, Testcontainers throws at fixture init; start Docker and rerun.

- [ ] **Step 9: Commit**

```bash
git add apps/api/.config apps/api/Accounting.slnx apps/api/Accounting.Api.Tests apps/api/Accounting.Api/Program.cs
git commit -m "test(api): add integration test harness with Testcontainers Postgres

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Domain model, DbContext, and migration

**Files:**
- Create: `apps/api/Accounting.Api/Domain/Enums/GenerationRunStatus.cs`
- Create: `apps/api/Accounting.Api/Domain/Enums/GenerationRunFileStatus.cs`
- Create: `apps/api/Accounting.Api/Domain/Entities/GenerationRun.cs`
- Create: `apps/api/Accounting.Api/Domain/Entities/GenerationRunFile.cs`
- Modify: `apps/api/Accounting.Api/Domain/Entities/Upload.cs`, `FilingPeriod.cs`, `OutputArtifact.cs`
- Modify: `apps/api/Accounting.Api/Data/AppDbContext.cs`
- Modify: `apps/api/Accounting.Api/Program.cs` (remove `using Accounting.Api.Workers;` and `AddHostedService<ParsePipelineWorker>()`)
- Delete: `Domain/Entities/ParseJob.cs`, `Domain/Enums/ParseJobStatus.cs`, `Workers/ParsePipelineWorker.cs`, `Controllers/UploadsController.cs`, `DTOs/Uploads/UploadDtos.cs`
- Create (generated): `Migrations/<timestamp>_GenerationRuns.cs`
- Test: `apps/api/Accounting.Api.Tests/MigrationTests.cs`

**Interfaces:**
- Produces: entities `GenerationRun`, `GenerationRunFile`; enums `GenerationRunStatus { Pending, Running, Completed, Failed }`, `GenerationRunFileStatus { Pending, Included, Failed }`; `AppDbContext.GenerationRuns`, `AppDbContext.GenerationRunFiles`; `OutputArtifact.GenerationRunId`; `FilingPeriod.GenerationRuns`; `Upload.RunFiles`.

Note: after this task the uploads endpoints do not exist until Task 3. That is acceptable on the feature branch; the build and tests stay green.

- [ ] **Step 1: Write the failing migration test**

Create `apps/api/Accounting.Api.Tests/MigrationTests.cs`:

```csharp
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `dotnet test apps/api/Accounting.slnx --filter FullyQualifiedName~MigrationTests`
Expected: FAIL, `generation_runs` not in tables.

- [ ] **Step 3: Add enums**

Create `apps/api/Accounting.Api/Domain/Enums/GenerationRunStatus.cs`:

```csharp
namespace Accounting.Api.Domain.Enums;

public enum GenerationRunStatus
{
    Pending = 1,
    Running = 2,
    Completed = 3,
    Failed = 4,
}
```

Create `apps/api/Accounting.Api/Domain/Enums/GenerationRunFileStatus.cs`:

```csharp
namespace Accounting.Api.Domain.Enums;

public enum GenerationRunFileStatus
{
    Pending = 1,
    Included = 2,
    Failed = 3,
}
```

- [ ] **Step 4: Add entities**

Create `apps/api/Accounting.Api/Domain/Entities/GenerationRun.cs`:

```csharp
using Accounting.Api.Domain.Enums;

namespace Accounting.Api.Domain.Entities;

public sealed class GenerationRun
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid ClientId { get; set; }
    public Guid FilingPeriodId { get; set; }
    public Guid RequestedByUserId { get; set; }
    public int Version { get; set; }
    public GenerationRunStatus Status { get; set; } = GenerationRunStatus.Pending;
    public string? ErrorMessage { get; set; }
    public DateTime CreatedAtUtc { get; set; } = DateTime.UtcNow;
    public DateTime? StartedAtUtc { get; set; }
    public DateTime? CompletedAtUtc { get; set; }

    public Client Client { get; set; } = null!;
    public FilingPeriod FilingPeriod { get; set; } = null!;
    public AppUser RequestedByUser { get; set; } = null!;
    public ICollection<GenerationRunFile> Files { get; set; } = new List<GenerationRunFile>();
    public ICollection<OutputArtifact> OutputArtifacts { get; set; } = new List<OutputArtifact>();
}
```

Create `apps/api/Accounting.Api/Domain/Entities/GenerationRunFile.cs`:

```csharp
using Accounting.Api.Domain.Enums;

namespace Accounting.Api.Domain.Entities;

public sealed class GenerationRunFile
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid GenerationRunId { get; set; }
    public Guid? UploadId { get; set; }
    public string OriginalFileName { get; set; } = string.Empty;
    public string SourceFileKind { get; set; } = string.Empty;
    public GenerationRunFileStatus Status { get; set; } = GenerationRunFileStatus.Pending;
    public string? ErrorMessage { get; set; }

    public GenerationRun GenerationRun { get; set; } = null!;
    public Upload? Upload { get; set; }
}
```

Edit `apps/api/Accounting.Api/Domain/Entities/Upload.cs`: replace the line
`public ICollection<ParseJob> ParseJobs { get; set; } = new List<ParseJob>();`
with
`public ICollection<GenerationRunFile> RunFiles { get; set; } = new List<GenerationRunFile>();`

Edit `apps/api/Accounting.Api/Domain/Entities/FilingPeriod.cs`: add after the `OutputArtifacts` line:
`public ICollection<GenerationRun> GenerationRuns { get; set; } = new List<GenerationRun>();`

Edit `apps/api/Accounting.Api/Domain/Entities/OutputArtifact.cs`:
- replace `public Guid ParseJobId { get; set; }` with `public Guid GenerationRunId { get; set; }`
- replace `public ParseJob ParseJob { get; set; } = null!;` with `public GenerationRun GenerationRun { get; set; } = null!;`

Delete: `Domain/Entities/ParseJob.cs`, `Domain/Enums/ParseJobStatus.cs`, `Workers/ParsePipelineWorker.cs`, `Controllers/UploadsController.cs`, `DTOs/Uploads/UploadDtos.cs`.

```bash
git rm apps/api/Accounting.Api/Domain/Entities/ParseJob.cs apps/api/Accounting.Api/Domain/Enums/ParseJobStatus.cs apps/api/Accounting.Api/Workers/ParsePipelineWorker.cs apps/api/Accounting.Api/Controllers/UploadsController.cs apps/api/Accounting.Api/DTOs/Uploads/UploadDtos.cs
```

In `Program.cs` remove the line `using Accounting.Api.Workers;` and the line `builder.Services.AddHostedService<ParsePipelineWorker>();`.

- [ ] **Step 5: Update AppDbContext**

In `apps/api/Accounting.Api/Data/AppDbContext.cs`:

Replace `public DbSet<ParseJob> ParseJobs => Set<ParseJob>();` with:

```csharp
    public DbSet<GenerationRun> GenerationRuns => Set<GenerationRun>();
    public DbSet<GenerationRunFile> GenerationRunFiles => Set<GenerationRunFile>();
```

Replace the entire `modelBuilder.Entity<ParseJob>(...)` block with:

```csharp
        modelBuilder.Entity<GenerationRun>(entity =>
        {
            entity.ToTable("generation_runs");
            entity.HasKey(x => x.Id);
            entity.Property(x => x.Version).IsRequired();
            entity.Property(x => x.Status)
                .HasConversion(
                    value => value.ToString(),
                    value => Enum.Parse<GenerationRunStatus>(value))
                .HasMaxLength(20)
                .IsRequired();
            entity.Property(x => x.ErrorMessage).HasMaxLength(2000);

            entity.HasIndex(x => new { x.FilingPeriodId, x.Version }).IsUnique();
            entity.HasIndex(x => x.FilingPeriodId)
                .IsUnique()
                .HasDatabaseName("IX_generation_runs_active_per_period")
                .HasFilter("\"Status\" IN ('Pending', 'Running')");
            entity.HasIndex(x => new { x.Status, x.CreatedAtUtc });

            entity.HasOne(x => x.Client)
                .WithMany()
                .HasForeignKey(x => x.ClientId)
                .OnDelete(DeleteBehavior.Cascade);
            entity.HasOne(x => x.FilingPeriod)
                .WithMany(x => x.GenerationRuns)
                .HasForeignKey(x => x.FilingPeriodId)
                .OnDelete(DeleteBehavior.Cascade);
            entity.HasOne(x => x.RequestedByUser)
                .WithMany()
                .HasForeignKey(x => x.RequestedByUserId)
                .OnDelete(DeleteBehavior.Restrict);
        });

        modelBuilder.Entity<GenerationRunFile>(entity =>
        {
            entity.ToTable("generation_run_files");
            entity.HasKey(x => x.Id);
            entity.Property(x => x.OriginalFileName).HasMaxLength(260).IsRequired();
            entity.Property(x => x.SourceFileKind).HasMaxLength(20).IsRequired();
            entity.Property(x => x.Status)
                .HasConversion(
                    value => value.ToString(),
                    value => Enum.Parse<GenerationRunFileStatus>(value))
                .HasMaxLength(20)
                .IsRequired();
            entity.Property(x => x.ErrorMessage).HasMaxLength(2000);
            entity.HasIndex(x => new { x.GenerationRunId, x.UploadId }).IsUnique();

            entity.HasOne(x => x.GenerationRun)
                .WithMany(x => x.Files)
                .HasForeignKey(x => x.GenerationRunId)
                .OnDelete(DeleteBehavior.Cascade);
            entity.HasOne(x => x.Upload)
                .WithMany(x => x.RunFiles)
                .HasForeignKey(x => x.UploadId)
                .OnDelete(DeleteBehavior.SetNull);
        });
```

In the `OutputArtifact` block, replace:

```csharp
            entity.HasOne(x => x.ParseJob)
                .WithMany(x => x.OutputArtifacts)
                .HasForeignKey(x => x.ParseJobId)
                .OnDelete(DeleteBehavior.Cascade);
```

with:

```csharp
            entity.HasOne(x => x.GenerationRun)
                .WithMany(x => x.OutputArtifacts)
                .HasForeignKey(x => x.GenerationRunId)
                .OnDelete(DeleteBehavior.Cascade);
```

- [ ] **Step 6: Build**

Run: `dotnet build apps/api/Accounting.slnx`
Expected: 0 errors. If anything still references `ParseJob`, `ParseJobStatus`, `ParsePipelineWorker`, or `DTOs.Uploads`, remove that reference.

- [ ] **Step 7: Generate the migration**

```bash
cd apps/api/Accounting.Api && dotnet ef migrations add GenerationRuns && cd ../../..
```

Expected: two new files in `Migrations/` named `<timestamp>_GenerationRuns.cs` and `.Designer.cs`, plus an updated `AppDbContextModelSnapshot.cs`. The connection string in `appsettings.json` is only used for design-time model building; no database is touched.

- [ ] **Step 8: Hand-edit the migration to drop placeholder artifacts first**

Open `Migrations/<timestamp>_GenerationRuns.cs`. As the very first statement inside `Up(MigrationBuilder migrationBuilder)`, before any `DropForeignKey`, add:

```csharp
            // Existing artifacts were produced by the placeholder per-file pipeline and have no value.
            // They must go before ParseJobId is replaced by a non-null GenerationRunId.
            migrationBuilder.Sql("DELETE FROM output_artifacts;");
```

Then verify the generated `Up` drops `FK_output_artifacts_parse_jobs_ParseJobId`, drops the `parse_jobs` table, replaces the `ParseJobId` column with `GenerationRunId`, creates `generation_runs` and `generation_run_files`, and creates the index `IX_generation_runs_active_per_period` with a `filter:` argument. If EF generated a `RenameColumn` from `ParseJobId` to `GenerationRunId`, that is fine.

- [ ] **Step 9: Run the migration tests**

Run: `dotnet test apps/api/Accounting.slnx`
Expected: all tests pass, including both `MigrationTests`.

- [ ] **Step 10: Commit**

```bash
git add -A apps/api
git commit -m "feat(api): add GenerationRun model, drop ParseJob, re-point artifacts

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Storage delete and Uploads feature

**Files:**
- Modify: `apps/api/Accounting.Api/Storage/IFileStorage.cs`, `LocalFileStorage.cs`, `AzureBlobFileStorage.cs`
- Create: `apps/api/Accounting.Api/Features/Uploads/UploadDtos.cs`
- Create: `apps/api/Accounting.Api/Features/Uploads/UploadsService.cs`
- Create: `apps/api/Accounting.Api/Features/Uploads/UploadsController.cs`
- Modify: `apps/api/Accounting.Api/Program.cs` (register service, JSON enum converter)
- Test: `apps/api/Accounting.Api.Tests/UploadsTests.cs`

**Interfaces:**
- Consumes: `AppDbContext.GenerationRuns`, `GenerationRunFiles`, `GenerationRunStatus` from Task 2.
- Produces: `IFileStorage.DeleteAsync(StoredFileReference, CancellationToken)`; `UploadDto(Guid Id, Guid FilingPeriodId, string OriginalFileName, string SourceFileKind, string ContentType, long SizeBytes, DateTime CreatedAtUtc, bool IncludedInLatestRun)`; `UploadsService` with `ListAsync`, `CreateAsync`, `DeleteAsync`; `DeleteUploadOutcome { Deleted, NotFound, ReferencedByActiveRun }`.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/Accounting.Api.Tests/UploadsTests.cs`:

```csharp
using System.Net;
using Accounting.Api.Data;
using Accounting.Api.Domain.Entities;
using Accounting.Api.Domain.Enums;
using Accounting.Api.Features.Uploads;
using Accounting.Api.Tests.Infrastructure;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Accounting.Api.Tests;

[Collection("api")]
public sealed class UploadsTests(PostgresFixture fixture)
{
    [Fact]
    public async Task Upload_creates_upload_and_no_run()
    {
        var client = await fixture.Factory.RegisterAndLoginAsync();
        var clientId = await client.CreateClientAsync();
        var periodId = await client.CreatePeriodAsync(clientId);

        var response = await client.UploadFileAsync(clientId, periodId);

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var dto = await response.ReadAsAsync<UploadDto>();
        Assert.Equal("factura.pdf", dto.OriginalFileName);
        Assert.False(dto.IncludedInLatestRun);

        await using var scope = fixture.Factory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        Assert.Equal(0, await db.GenerationRuns.CountAsync(r => r.FilingPeriodId == periodId));
    }

    [Fact]
    public async Task List_returns_uploads_newest_first()
    {
        var client = await fixture.Factory.RegisterAndLoginAsync();
        var clientId = await client.CreateClientAsync();
        var periodId = await client.CreatePeriodAsync(clientId);
        await client.UploadFileAsync(clientId, periodId, "a.pdf");
        await client.UploadFileAsync(clientId, periodId, "b.pdf");

        var list = await (await client.GetAsync($"/api/clients/{clientId}/periods/{periodId}/uploads")).ReadAsAsync<List<UploadDto>>();

        Assert.Equal(2, list.Count);
        Assert.Equal("b.pdf", list[0].OriginalFileName);
    }

    [Fact]
    public async Task Delete_removes_row_and_storage_object()
    {
        var client = await fixture.Factory.RegisterAndLoginAsync();
        var clientId = await client.CreateClientAsync();
        var periodId = await client.CreatePeriodAsync(clientId);
        var dto = await (await client.UploadFileAsync(clientId, periodId)).ReadAsAsync<UploadDto>();

        string storagePath;
        await using (var scope = fixture.Factory.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
            var upload = await db.Uploads.SingleAsync(u => u.Id == dto.Id);
            storagePath = Path.Combine(fixture.Factory.StorageRoot, upload.StorageContainer, upload.StoragePath);
        }
        Assert.True(File.Exists(storagePath));

        var response = await client.DeleteAsync($"/api/clients/{clientId}/periods/{periodId}/uploads/{dto.Id}");

        Assert.Equal(HttpStatusCode.NoContent, response.StatusCode);
        Assert.False(File.Exists(storagePath));
        await using var verify = fixture.Factory.CreateScope();
        var verifyDb = verify.ServiceProvider.GetRequiredService<AppDbContext>();
        Assert.False(await verifyDb.Uploads.AnyAsync(u => u.Id == dto.Id));
    }

    [Fact]
    public async Task Delete_returns_409_when_referenced_by_active_run()
    {
        var client = await fixture.Factory.RegisterAndLoginAsync();
        var clientId = await client.CreateClientAsync();
        var periodId = await client.CreatePeriodAsync(clientId);
        var dto = await (await client.UploadFileAsync(clientId, periodId)).ReadAsAsync<UploadDto>();

        await using (var scope = fixture.Factory.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
            var period = await db.FilingPeriods.Include(p => p.Client).SingleAsync(p => p.Id == periodId);
            db.GenerationRuns.Add(new GenerationRun
            {
                ClientId = clientId,
                FilingPeriodId = periodId,
                RequestedByUserId = period.Client.OwnerUserId,
                Version = 1,
                Status = GenerationRunStatus.Pending,
                Files = { new GenerationRunFile { UploadId = dto.Id, OriginalFileName = dto.OriginalFileName, SourceFileKind = dto.SourceFileKind } },
            });
            await db.SaveChangesAsync();
        }

        var response = await client.DeleteAsync($"/api/clients/{clientId}/periods/{periodId}/uploads/{dto.Id}");

        Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
    }

    [Fact]
    public async Task Other_user_gets_404_on_list_and_delete()
    {
        var owner = await fixture.Factory.RegisterAndLoginAsync();
        var clientId = await owner.CreateClientAsync();
        var periodId = await owner.CreatePeriodAsync(clientId);
        var dto = await (await owner.UploadFileAsync(clientId, periodId)).ReadAsAsync<UploadDto>();

        var intruder = await fixture.Factory.RegisterAndLoginAsync();

        var list = await intruder.GetAsync($"/api/clients/{clientId}/periods/{periodId}/uploads");
        var delete = await intruder.DeleteAsync($"/api/clients/{clientId}/periods/{periodId}/uploads/{dto.Id}");

        Assert.Equal(HttpStatusCode.NotFound, list.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, delete.StatusCode);
    }
}
```

- [ ] **Step 2: Run to verify they fail**

Run: `dotnet test apps/api/Accounting.slnx --filter FullyQualifiedName~UploadsTests`
Expected: build error, `Accounting.Api.Features.Uploads` does not exist.

- [ ] **Step 3: Add `DeleteAsync` to storage**

In `apps/api/Accounting.Api/Storage/IFileStorage.cs` add to the interface:

```csharp
    Task DeleteAsync(StoredFileReference file, CancellationToken cancellationToken = default);
```

In `LocalFileStorage.cs` add:

```csharp
    public Task DeleteAsync(StoredFileReference file, CancellationToken cancellationToken = default)
    {
        var fullPath = Path.Combine(_options.LocalRootPath, file.Container, file.Path.Replace('/', Path.DirectorySeparatorChar));
        if (File.Exists(fullPath))
        {
            File.Delete(fullPath);
        }

        return Task.CompletedTask;
    }
```

In `AzureBlobFileStorage.cs` add:

```csharp
    public async Task DeleteAsync(StoredFileReference file, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(_options.AzureBlobConnectionString))
        {
            throw new InvalidOperationException("Storage:AzureBlobConnectionString no está configurado.");
        }

        var client = new BlobContainerClient(_options.AzureBlobConnectionString, file.Container);
        await client.GetBlobClient(file.Path).DeleteIfExistsAsync(cancellationToken: cancellationToken);
    }
```

- [ ] **Step 4: Create DTOs**

Create `apps/api/Accounting.Api/Features/Uploads/UploadDtos.cs`:

```csharp
using System.ComponentModel.DataAnnotations;

namespace Accounting.Api.Features.Uploads;

public sealed class CreateUploadRequestDto
{
    [Required]
    public IFormFile File { get; init; } = null!;

    [Required]
    [RegularExpression("^(Excel|PDF)$", ErrorMessage = "El tipo debe ser Excel o PDF.")]
    public string SourceFileKind { get; init; } = string.Empty;
}

public sealed record UploadDto(
    Guid Id,
    Guid FilingPeriodId,
    string OriginalFileName,
    string SourceFileKind,
    string ContentType,
    long SizeBytes,
    DateTime CreatedAtUtc,
    bool IncludedInLatestRun);
```

- [ ] **Step 5: Create the service**

Create `apps/api/Accounting.Api/Features/Uploads/UploadsService.cs`:

```csharp
using Accounting.Api.Data;
using Accounting.Api.Domain.Entities;
using Accounting.Api.Domain.Enums;
using Accounting.Api.Storage;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace Accounting.Api.Features.Uploads;

public enum DeleteUploadOutcome
{
    Deleted,
    NotFound,
    ReferencedByActiveRun,
}

public sealed class UploadsService(
    AppDbContext dbContext,
    IFileStorage fileStorage,
    IOptions<StorageOptions> storageOptions)
{
    private readonly StorageOptions _storageOptions = storageOptions.Value;

    public async Task<IReadOnlyList<UploadDto>?> ListAsync(Guid clientId, Guid filingPeriodId, Guid userId, CancellationToken cancellationToken)
    {
        var period = await dbContext.FindOwnedFilingPeriodAsync(clientId, filingPeriodId, userId, cancellationToken);
        if (period is null)
        {
            return null;
        }

        var included = await IncludedInLatestRunAsync(filingPeriodId, cancellationToken);

        var uploads = await dbContext.Uploads
            .AsNoTracking()
            .Where(x => x.ClientId == clientId && x.FilingPeriodId == filingPeriodId)
            .OrderByDescending(x => x.CreatedAtUtc)
            .ToListAsync(cancellationToken);

        return uploads.Select(x => ToDto(x, included.Contains(x.Id))).ToList();
    }

    public async Task<UploadDto?> CreateAsync(
        Guid clientId,
        Guid filingPeriodId,
        Guid userId,
        IFormFile file,
        string sourceFileKind,
        CancellationToken cancellationToken)
    {
        var period = await dbContext.FindOwnedFilingPeriodAsync(clientId, filingPeriodId, userId, cancellationToken);
        if (period is null)
        {
            return null;
        }

        var extension = Path.GetExtension(file.FileName).ToLowerInvariant();
        var safeFileName = SanitizeFileName(Path.GetFileNameWithoutExtension(file.FileName));
        var path = $"{clientId}/{period.Year:D4}/{period.Month:D2}/{Guid.NewGuid()}_{safeFileName}{extension}";

        await using var stream = file.OpenReadStream();
        var stored = await fileStorage.SaveAsync(_storageOptions.UploadContainer, path, stream, file.ContentType, cancellationToken);

        var upload = new Upload
        {
            ClientId = clientId,
            FilingPeriodId = filingPeriodId,
            UploadedByUserId = userId,
            OriginalFileName = file.FileName,
            ContentType = file.ContentType,
            SourceFileKind = sourceFileKind,
            SizeBytes = file.Length,
            StorageProvider = stored.Provider,
            StorageContainer = stored.Container,
            StoragePath = stored.Path,
        };

        dbContext.Uploads.Add(upload);
        await dbContext.SaveChangesAsync(cancellationToken);

        return ToDto(upload, includedInLatestRun: false);
    }

    public async Task<DeleteUploadOutcome> DeleteAsync(Guid clientId, Guid filingPeriodId, Guid uploadId, Guid userId, CancellationToken cancellationToken)
    {
        var period = await dbContext.FindOwnedFilingPeriodAsync(clientId, filingPeriodId, userId, cancellationToken);
        if (period is null)
        {
            return DeleteUploadOutcome.NotFound;
        }

        var upload = await dbContext.Uploads
            .FirstOrDefaultAsync(x => x.Id == uploadId && x.FilingPeriodId == filingPeriodId && x.ClientId == clientId, cancellationToken);
        if (upload is null)
        {
            return DeleteUploadOutcome.NotFound;
        }

        var referencedByActiveRun = await dbContext.GenerationRunFiles
            .AnyAsync(f => f.UploadId == uploadId
                           && (f.GenerationRun.Status == GenerationRunStatus.Pending || f.GenerationRun.Status == GenerationRunStatus.Running),
                cancellationToken);
        if (referencedByActiveRun)
        {
            return DeleteUploadOutcome.ReferencedByActiveRun;
        }

        await fileStorage.DeleteAsync(new StoredFileReference(upload.StorageProvider, upload.StorageContainer, upload.StoragePath), cancellationToken);

        dbContext.Uploads.Remove(upload);
        await dbContext.SaveChangesAsync(cancellationToken);
        return DeleteUploadOutcome.Deleted;
    }

    public static bool IsValidFileType(string fileName, string sourceFileKind)
    {
        var extension = Path.GetExtension(fileName).ToLowerInvariant();
        return sourceFileKind switch
        {
            "Excel" => extension is ".xls" or ".xlsx",
            "PDF" => extension == ".pdf",
            _ => false,
        };
    }

    private async Task<HashSet<Guid>> IncludedInLatestRunAsync(Guid filingPeriodId, CancellationToken cancellationToken)
    {
        var latestCompletedRunId = await dbContext.GenerationRuns
            .Where(r => r.FilingPeriodId == filingPeriodId && r.Status == GenerationRunStatus.Completed)
            .OrderByDescending(r => r.Version)
            .Select(r => (Guid?)r.Id)
            .FirstOrDefaultAsync(cancellationToken);

        if (latestCompletedRunId is null)
        {
            return [];
        }

        var ids = await dbContext.GenerationRunFiles
            .Where(f => f.GenerationRunId == latestCompletedRunId && f.UploadId != null)
            .Select(f => f.UploadId!.Value)
            .ToListAsync(cancellationToken);

        return ids.ToHashSet();
    }

    private static UploadDto ToDto(Upload x, bool includedInLatestRun) => new(
        x.Id,
        x.FilingPeriodId,
        x.OriginalFileName,
        x.SourceFileKind,
        x.ContentType,
        x.SizeBytes,
        x.CreatedAtUtc,
        includedInLatestRun);

    private static string SanitizeFileName(string fileName)
    {
        var invalidChars = Path.GetInvalidFileNameChars();
        var cleaned = new string(fileName.Select(c => invalidChars.Contains(c) ? '_' : c).ToArray());
        return string.IsNullOrWhiteSpace(cleaned) ? "archivo" : cleaned;
    }
}
```

- [ ] **Step 6: Create the controller**

Create `apps/api/Accounting.Api/Features/Uploads/UploadsController.cs`:

```csharp
using Accounting.Api.Auth;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Accounting.Api.Features.Uploads;

[ApiController]
[Authorize]
[Route("api/clients/{clientId:guid}/periods/{filingPeriodId:guid}/uploads")]
public sealed class UploadsController(
    UploadsService uploadsService,
    ICurrentUserService currentUserService) : ControllerBase
{
    [HttpGet]
    [ProducesResponseType<IReadOnlyList<UploadDto>>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> List(Guid clientId, Guid filingPeriodId, CancellationToken cancellationToken)
    {
        var uploads = await uploadsService.ListAsync(clientId, filingPeriodId, currentUserService.UserId!.Value, cancellationToken);
        return uploads is null ? NotFound() : Ok(uploads);
    }

    [HttpPost]
    [RequestSizeLimit(20_000_000)]
    [ProducesResponseType<UploadDto>(StatusCodes.Status201Created)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Upload(Guid clientId, Guid filingPeriodId, [FromForm] CreateUploadRequestDto request, CancellationToken cancellationToken)
    {
        if (request.File.Length <= 0)
        {
            return BadRequest(new ValidationProblemDetails(new Dictionary<string, string[]>
            {
                ["file"] = ["El archivo está vacío."],
            }));
        }

        if (!UploadsService.IsValidFileType(request.File.FileName, request.SourceFileKind))
        {
            return BadRequest(new ValidationProblemDetails(new Dictionary<string, string[]>
            {
                ["file"] = ["El tipo de archivo no corresponde al tipo seleccionado (Excel/PDF)."],
            }));
        }

        var upload = await uploadsService.CreateAsync(
            clientId, filingPeriodId, currentUserService.UserId!.Value, request.File, request.SourceFileKind, cancellationToken);

        if (upload is null)
        {
            return NotFound();
        }

        return Created($"/api/clients/{clientId}/periods/{filingPeriodId}/uploads/{upload.Id}", upload);
    }

    [HttpDelete("{uploadId:guid}")]
    [ProducesResponseType(StatusCodes.Status204NoContent)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    public async Task<IActionResult> Delete(Guid clientId, Guid filingPeriodId, Guid uploadId, CancellationToken cancellationToken)
    {
        var outcome = await uploadsService.DeleteAsync(clientId, filingPeriodId, uploadId, currentUserService.UserId!.Value, cancellationToken);

        return outcome switch
        {
            DeleteUploadOutcome.Deleted => NoContent(),
            DeleteUploadOutcome.ReferencedByActiveRun => Conflict(new ProblemDetails
            {
                Title = "El archivo está siendo usado por una generación en curso.",
                Status = StatusCodes.Status409Conflict,
            }),
            _ => NotFound(),
        };
    }
}
```

- [ ] **Step 7: Register the service and string enums in Program.cs**

In `Program.cs`, replace `builder.Services.AddControllers();` with:

```csharp
builder.Services
    .AddControllers()
    .AddJsonOptions(options =>
    {
        options.JsonSerializerOptions.Converters.Add(new System.Text.Json.Serialization.JsonStringEnumConverter());
    });

builder.Services.AddScoped<Accounting.Api.Features.Uploads.UploadsService>();
```

Note: `IFileStorage` is registered as a singleton with a manually created `StorageOptions`; `UploadsService` takes `IOptions<StorageOptions>` which is bound from the same section by `Configure<StorageOptions>`, so both see the same values.

- [ ] **Step 8: Run the tests**

Run: `dotnet test apps/api/Accounting.slnx`
Expected: all pass, including 5 `UploadsTests`.

- [ ] **Step 9: Commit**

```bash
git add -A apps/api
git commit -m "feat(api): uploads feature with delete and includedInLatestRun

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Generation runs endpoints

**Files:**
- Create: `apps/api/Accounting.Api/Features/Generation/GenerationRunDtos.cs`
- Create: `apps/api/Accounting.Api/Features/Generation/GenerationRunsService.cs`
- Create: `apps/api/Accounting.Api/Features/Generation/GenerationRunsController.cs`
- Modify: `apps/api/Accounting.Api/Program.cs` (register service)
- Test: `apps/api/Accounting.Api.Tests/GenerationRunsTests.cs`

**Interfaces:**
- Consumes: entities and enums from Task 2; `UploadDto` from Task 3.
- Produces: `GenerationRunDto(Guid Id, Guid FilingPeriodId, int Version, GenerationRunStatus Status, string? ErrorMessage, DateTime CreatedAtUtc, DateTime? StartedAtUtc, DateTime? CompletedAtUtc, IReadOnlyList<GenerationRunFileDto> Files, IReadOnlyList<OutputArtifactDto> Artifacts)`; `GenerationRunFileDto(Guid? UploadId, string OriginalFileName, string SourceFileKind, GenerationRunFileStatus Status, string? ErrorMessage)`; `OutputArtifactDto(Guid Id, string ArtifactKind, string FileName, DateTime CreatedAtUtc, long SizeBytes)`; `GenerationRunsService.CreateAsync`, `ListAsync`, `GetAsync`; `CreateRunOutcome { Created, PeriodNotFound, NoUploads, ActiveRunExists }`; `GenerationRunsService.ToDto(GenerationRun)` static.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/Accounting.Api.Tests/GenerationRunsTests.cs`:

```csharp
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `dotnet test apps/api/Accounting.slnx --filter FullyQualifiedName~GenerationRunsTests`
Expected: build error, `Accounting.Api.Features.Generation` does not exist.

- [ ] **Step 3: Create DTOs**

Create `apps/api/Accounting.Api/Features/Generation/GenerationRunDtos.cs`:

```csharp
using Accounting.Api.Domain.Enums;

namespace Accounting.Api.Features.Generation;

public sealed record OutputArtifactDto(
    Guid Id,
    string ArtifactKind,
    string FileName,
    DateTime CreatedAtUtc,
    long SizeBytes);

public sealed record GenerationRunFileDto(
    Guid? UploadId,
    string OriginalFileName,
    string SourceFileKind,
    GenerationRunFileStatus Status,
    string? ErrorMessage);

public sealed record GenerationRunDto(
    Guid Id,
    Guid FilingPeriodId,
    int Version,
    GenerationRunStatus Status,
    string? ErrorMessage,
    DateTime CreatedAtUtc,
    DateTime? StartedAtUtc,
    DateTime? CompletedAtUtc,
    IReadOnlyList<GenerationRunFileDto> Files,
    IReadOnlyList<OutputArtifactDto> Artifacts);
```

- [ ] **Step 4: Create the service**

Create `apps/api/Accounting.Api/Features/Generation/GenerationRunsService.cs`:

```csharp
using Accounting.Api.Data;
using Accounting.Api.Domain.Entities;
using Accounting.Api.Domain.Enums;
using Microsoft.EntityFrameworkCore;
using Npgsql;

namespace Accounting.Api.Features.Generation;

public enum CreateRunOutcome
{
    Created,
    PeriodNotFound,
    NoUploads,
    ActiveRunExists,
}

public sealed record CreateRunResult(CreateRunOutcome Outcome, GenerationRunDto? Run);

public sealed class GenerationRunsService(AppDbContext dbContext)
{
    public async Task<CreateRunResult> CreateAsync(Guid clientId, Guid filingPeriodId, Guid userId, CancellationToken cancellationToken)
    {
        var period = await dbContext.FindOwnedFilingPeriodAsync(clientId, filingPeriodId, userId, cancellationToken);
        if (period is null)
        {
            return new CreateRunResult(CreateRunOutcome.PeriodNotFound, null);
        }

        var uploads = await dbContext.Uploads
            .AsNoTracking()
            .Where(u => u.FilingPeriodId == filingPeriodId && u.ClientId == clientId)
            .OrderBy(u => u.CreatedAtUtc)
            .ToListAsync(cancellationToken);
        if (uploads.Count == 0)
        {
            return new CreateRunResult(CreateRunOutcome.NoUploads, null);
        }

        var activeExists = await dbContext.GenerationRuns.AnyAsync(
            r => r.FilingPeriodId == filingPeriodId
                 && (r.Status == GenerationRunStatus.Pending || r.Status == GenerationRunStatus.Running),
            cancellationToken);
        if (activeExists)
        {
            return new CreateRunResult(CreateRunOutcome.ActiveRunExists, null);
        }

        var maxVersion = await dbContext.GenerationRuns
            .Where(r => r.FilingPeriodId == filingPeriodId)
            .MaxAsync(r => (int?)r.Version, cancellationToken) ?? 0;

        var run = new GenerationRun
        {
            ClientId = clientId,
            FilingPeriodId = filingPeriodId,
            RequestedByUserId = userId,
            Version = maxVersion + 1,
            Status = GenerationRunStatus.Pending,
        };
        foreach (var upload in uploads)
        {
            run.Files.Add(new GenerationRunFile
            {
                UploadId = upload.Id,
                OriginalFileName = upload.OriginalFileName,
                SourceFileKind = upload.SourceFileKind,
            });
        }

        dbContext.GenerationRuns.Add(run);
        try
        {
            await dbContext.SaveChangesAsync(cancellationToken);
        }
        catch (DbUpdateException ex) when (ex.InnerException is PostgresException { SqlState: PostgresErrorCodes.UniqueViolation })
        {
            return new CreateRunResult(CreateRunOutcome.ActiveRunExists, null);
        }

        return new CreateRunResult(CreateRunOutcome.Created, ToDto(run));
    }

    public async Task<IReadOnlyList<GenerationRunDto>?> ListAsync(Guid clientId, Guid filingPeriodId, Guid userId, CancellationToken cancellationToken)
    {
        var period = await dbContext.FindOwnedFilingPeriodAsync(clientId, filingPeriodId, userId, cancellationToken);
        if (period is null)
        {
            return null;
        }

        var runs = await RunsQuery()
            .Where(r => r.FilingPeriodId == filingPeriodId)
            .OrderByDescending(r => r.Version)
            .ToListAsync(cancellationToken);

        return runs.Select(ToDto).ToList();
    }

    public async Task<GenerationRunDto?> GetAsync(Guid clientId, Guid filingPeriodId, Guid runId, Guid userId, CancellationToken cancellationToken)
    {
        var period = await dbContext.FindOwnedFilingPeriodAsync(clientId, filingPeriodId, userId, cancellationToken);
        if (period is null)
        {
            return null;
        }

        var run = await RunsQuery()
            .FirstOrDefaultAsync(r => r.Id == runId && r.FilingPeriodId == filingPeriodId, cancellationToken);

        return run is null ? null : ToDto(run);
    }

    private IQueryable<GenerationRun> RunsQuery() => dbContext.GenerationRuns
        .AsNoTracking()
        .Include(r => r.Files)
        .Include(r => r.OutputArtifacts);

    public static GenerationRunDto ToDto(GenerationRun run) => new(
        run.Id,
        run.FilingPeriodId,
        run.Version,
        run.Status,
        run.ErrorMessage,
        run.CreatedAtUtc,
        run.StartedAtUtc,
        run.CompletedAtUtc,
        run.Files
            .OrderBy(f => f.OriginalFileName)
            .Select(f => new GenerationRunFileDto(f.UploadId, f.OriginalFileName, f.SourceFileKind, f.Status, f.ErrorMessage))
            .ToList(),
        run.OutputArtifacts
            .OrderByDescending(a => a.CreatedAtUtc)
            .Select(a => new OutputArtifactDto(a.Id, a.ArtifactKind, a.FileName, a.CreatedAtUtc, a.SizeBytes))
            .ToList());
}
```

- [ ] **Step 5: Create the controller**

Create `apps/api/Accounting.Api/Features/Generation/GenerationRunsController.cs`:

```csharp
using Accounting.Api.Auth;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Accounting.Api.Features.Generation;

[ApiController]
[Authorize]
[Route("api/clients/{clientId:guid}/periods/{filingPeriodId:guid}/runs")]
public sealed class GenerationRunsController(
    GenerationRunsService runsService,
    ICurrentUserService currentUserService) : ControllerBase
{
    [HttpPost]
    [ProducesResponseType<GenerationRunDto>(StatusCodes.Status202Accepted)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    public async Task<IActionResult> Create(Guid clientId, Guid filingPeriodId, CancellationToken cancellationToken)
    {
        var result = await runsService.CreateAsync(clientId, filingPeriodId, currentUserService.UserId!.Value, cancellationToken);

        return result.Outcome switch
        {
            CreateRunOutcome.Created => Accepted($"/api/clients/{clientId}/periods/{filingPeriodId}/runs/{result.Run!.Id}", result.Run),
            CreateRunOutcome.NoUploads => BadRequest(new ValidationProblemDetails(new Dictionary<string, string[]>
            {
                ["uploads"] = ["El período no tiene archivos para generar."],
            })),
            CreateRunOutcome.ActiveRunExists => Conflict(new ProblemDetails
            {
                Title = "Ya existe una generación en curso para este período.",
                Status = StatusCodes.Status409Conflict,
            }),
            _ => NotFound(),
        };
    }

    [HttpGet]
    [ProducesResponseType<IReadOnlyList<GenerationRunDto>>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> List(Guid clientId, Guid filingPeriodId, CancellationToken cancellationToken)
    {
        var runs = await runsService.ListAsync(clientId, filingPeriodId, currentUserService.UserId!.Value, cancellationToken);
        return runs is null ? NotFound() : Ok(runs);
    }

    [HttpGet("{runId:guid}")]
    [ProducesResponseType<GenerationRunDto>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Get(Guid clientId, Guid filingPeriodId, Guid runId, CancellationToken cancellationToken)
    {
        var run = await runsService.GetAsync(clientId, filingPeriodId, runId, currentUserService.UserId!.Value, cancellationToken);
        return run is null ? NotFound() : Ok(run);
    }
}
```

- [ ] **Step 6: Register the service**

In `Program.cs`, after `builder.Services.AddScoped<Accounting.Api.Features.Uploads.UploadsService>();` add:

```csharp
builder.Services.AddScoped<Accounting.Api.Features.Generation.GenerationRunsService>();
```

- [ ] **Step 7: Run the tests**

Run: `dotnet test apps/api/Accounting.slnx`
Expected: all pass, including 6 `GenerationRunsTests`.

- [ ] **Step 8: Commit**

```bash
git add -A apps/api
git commit -m "feat(api): generation run endpoints with versioning and active-run guard

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Processor, placeholder generator, and worker

**Files:**
- Create: `apps/api/Accounting.Api/Features/Generation/GenerationOptions.cs`
- Create: `apps/api/Accounting.Api/Features/Generation/ICsvGenerator.cs`
- Create: `apps/api/Accounting.Api/Features/Generation/PlaceholderCsvGenerator.cs`
- Create: `apps/api/Accounting.Api/Features/Generation/GenerationRunProcessor.cs`
- Create: `apps/api/Accounting.Api/Features/Generation/GenerationWorker.cs`
- Modify: `apps/api/Accounting.Api/Program.cs` (options, DI, hosted service)
- Test: `apps/api/Accounting.Api.Tests/GenerationProcessorTests.cs`

**Interfaces:**
- Consumes: `IFileStorage`, `StorageOptions`, entities from Task 2, `GenerationRunsService.ToDto` from Task 4.
- Produces: `GenerationOptions { PollIntervalSeconds, RunTimeoutMinutes }`; `ICsvGenerator.GenerateAsync(GenerationContext, CancellationToken) : Task<IReadOnlyList<GeneratedFile>>`; `GenerationRunProcessor.TryClaimAsync(ct) : Task<Guid?>`, `RecoverStuckRunsAsync(ct) : Task<int>`, `ProcessAsync(Guid runId, ct) : Task`; `GenerationWorker : BackgroundService`.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/Accounting.Api.Tests/GenerationProcessorTests.cs`:

```csharp
using System.Net;
using Accounting.Api.Data;
using Accounting.Api.Domain.Enums;
using Accounting.Api.Features.Generation;
using Accounting.Api.Features.Uploads;
using Accounting.Api.Tests.Infrastructure;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Accounting.Api.Tests;

[Collection("api")]
public sealed class GenerationProcessorTests(PostgresFixture fixture)
{
    private static string RunsUrl(Guid clientId, Guid periodId) => $"/api/clients/{clientId}/periods/{periodId}/runs";

    private async Task<(HttpClient Client, Guid ClientId, Guid PeriodId)> SetupPeriodWithFilesAsync(params string[] fileNames)
    {
        var client = await fixture.Factory.RegisterAndLoginAsync();
        var clientId = await client.CreateClientAsync();
        var periodId = await client.CreatePeriodAsync(clientId, 2026, Random.Shared.Next(1, 13));
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `dotnet test apps/api/Accounting.slnx --filter FullyQualifiedName~GenerationProcessorTests`
Expected: build error, `GenerationRunProcessor` does not exist.

- [ ] **Step 3: Options and generator seam**

Create `apps/api/Accounting.Api/Features/Generation/GenerationOptions.cs`:

```csharp
using System.ComponentModel.DataAnnotations;

namespace Accounting.Api.Features.Generation;

public sealed class GenerationOptions
{
    public const string SectionName = "Generation";

    [Range(1, 300)]
    public int PollIntervalSeconds { get; set; } = 3;

    [Range(1, 1440)]
    public int RunTimeoutMinutes { get; set; } = 10;
}
```

Create `apps/api/Accounting.Api/Features/Generation/ICsvGenerator.cs`:

```csharp
namespace Accounting.Api.Features.Generation;

public sealed record GenerationSourceFile(
    Guid? UploadId,
    string OriginalFileName,
    string SourceFileKind,
    long SizeBytes,
    Func<CancellationToken, Task<Stream>> OpenRead);

public sealed record GenerationContext(
    Guid ClientId,
    int Year,
    int Month,
    int Version,
    IReadOnlyList<GenerationSourceFile> Files);

public sealed record GeneratedFile(string FileName, string ContentType, Stream Content);

public interface ICsvGenerator
{
    Task<IReadOnlyList<GeneratedFile>> GenerateAsync(GenerationContext context, CancellationToken cancellationToken);
}
```

Create `apps/api/Accounting.Api/Features/Generation/PlaceholderCsvGenerator.cs`:

```csharp
using System.Text;

namespace Accounting.Api.Features.Generation;

/// <summary>
/// Temporary generator: one row per included source file. Replace with the real
/// Hacienda parser behind <see cref="ICsvGenerator"/>; nothing else needs to change.
/// </summary>
public sealed class PlaceholderCsvGenerator : ICsvGenerator
{
    public Task<IReadOnlyList<GeneratedFile>> GenerateAsync(GenerationContext context, CancellationToken cancellationToken)
    {
        var builder = new StringBuilder();
        builder.AppendLine("cliente_id,anio,mes,version,archivo_origen,tipo,tamano_bytes");
        foreach (var file in context.Files)
        {
            builder.AppendLine($"{context.ClientId},{context.Year},{context.Month},{context.Version},\"{file.OriginalFileName.Replace("\"", "\"\"")}\",{file.SourceFileKind},{file.SizeBytes}");
        }

        var bytes = Encoding.UTF8.GetBytes(builder.ToString());
        var fileName = $"resultado_{context.Year:D4}_{context.Month:D2}_v{context.Version}.csv";
        IReadOnlyList<GeneratedFile> result = [new GeneratedFile(fileName, "text/csv", new MemoryStream(bytes))];
        return Task.FromResult(result);
    }
}
```

- [ ] **Step 4: Processor**

Create `apps/api/Accounting.Api/Features/Generation/GenerationRunProcessor.cs`:

```csharp
using Accounting.Api.Data;
using Accounting.Api.Domain.Entities;
using Accounting.Api.Domain.Enums;
using Accounting.Api.Storage;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace Accounting.Api.Features.Generation;

public sealed class GenerationRunProcessor(
    AppDbContext dbContext,
    IFileStorage fileStorage,
    ICsvGenerator csvGenerator,
    IOptions<StorageOptions> storageOptions,
    IOptions<GenerationOptions> generationOptions,
    ILogger<GenerationRunProcessor> logger)
{
    private const string ClaimSql = """
        UPDATE generation_runs
        SET "Status" = 'Running', "StartedAtUtc" = now()
        WHERE "Id" = (
            SELECT "Id" FROM generation_runs
            WHERE "Status" = 'Pending'
            ORDER BY "CreatedAtUtc"
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        )
        RETURNING "Id";
        """;

    private readonly StorageOptions _storage = storageOptions.Value;
    private readonly GenerationOptions _generation = generationOptions.Value;

    /// <summary>Atomically moves the oldest Pending run to Running. Returns null when nothing is pending.</summary>
    public async Task<Guid?> TryClaimAsync(CancellationToken cancellationToken)
    {
        var connection = dbContext.Database.GetDbConnection();
        if (connection.State != System.Data.ConnectionState.Open)
        {
            await connection.OpenAsync(cancellationToken);
        }

        await using var command = connection.CreateCommand();
        command.CommandText = ClaimSql;
        var result = await command.ExecuteScalarAsync(cancellationToken);
        return result is Guid id ? id : null;
    }

    /// <summary>Fails runs stuck in Running longer than the configured timeout. Returns how many were failed.</summary>
    public async Task<int> RecoverStuckRunsAsync(CancellationToken cancellationToken)
    {
        var cutoff = DateTime.UtcNow.AddMinutes(-_generation.RunTimeoutMinutes);
        var now = DateTime.UtcNow;
        var message = $"La generación excedió el tiempo máximo de {_generation.RunTimeoutMinutes} minutos.";

        var recovered = await dbContext.GenerationRuns
            .Where(r => r.Status == GenerationRunStatus.Running && r.StartedAtUtc != null && r.StartedAtUtc < cutoff)
            .ExecuteUpdateAsync(s => s
                .SetProperty(r => r.Status, GenerationRunStatus.Failed)
                .SetProperty(r => r.CompletedAtUtc, now)
                .SetProperty(r => r.ErrorMessage, message), cancellationToken);

        if (recovered > 0)
        {
            logger.LogWarning("Se marcaron {Count} generaciones atascadas como fallidas.", recovered);
        }

        return recovered;
    }

    public async Task ProcessAsync(Guid runId, CancellationToken cancellationToken)
    {
        var run = await dbContext.GenerationRuns
            .Include(r => r.FilingPeriod)
            .Include(r => r.Files).ThenInclude(f => f.Upload)
            .FirstOrDefaultAsync(r => r.Id == runId, cancellationToken);

        if (run is null)
        {
            logger.LogWarning("Generación {RunId} no encontrada al procesar.", runId);
            return;
        }

        try
        {
            var sources = new List<GenerationSourceFile>();
            foreach (var file in run.Files.OrderBy(f => f.OriginalFileName))
            {
                if (file.Upload is null)
                {
                    file.Status = GenerationRunFileStatus.Failed;
                    file.ErrorMessage = "El archivo fue eliminado antes de generar.";
                    continue;
                }

                var reference = new StoredFileReference(file.Upload.StorageProvider, file.Upload.StorageContainer, file.Upload.StoragePath);
                var probe = await fileStorage.OpenReadAsync(reference, cancellationToken);
                if (probe is null)
                {
                    file.Status = GenerationRunFileStatus.Failed;
                    file.ErrorMessage = "No se encontró el archivo en el almacenamiento.";
                    continue;
                }

                await probe.DisposeAsync();
                file.Status = GenerationRunFileStatus.Included;
                sources.Add(new GenerationSourceFile(
                    file.UploadId,
                    file.OriginalFileName,
                    file.SourceFileKind,
                    file.Upload.SizeBytes,
                    async ct => await fileStorage.OpenReadAsync(reference, ct)
                                ?? throw new FileNotFoundException(file.OriginalFileName)));
            }

            if (sources.Count == 0)
            {
                Fail(run, "Ningún archivo del período pudo ser leído.");
                await dbContext.SaveChangesAsync(cancellationToken);
                return;
            }

            var context = new GenerationContext(run.ClientId, run.FilingPeriod.Year, run.FilingPeriod.Month, run.Version, sources);
            var generated = await csvGenerator.GenerateAsync(context, cancellationToken);

            foreach (var output in generated)
            {
                await using var content = output.Content;
                var size = content.CanSeek ? content.Length : -1;
                var path = $"{run.ClientId}/{run.FilingPeriod.Year:D4}/{run.FilingPeriod.Month:D2}/run-{run.Version}/{output.FileName}";
                var stored = await fileStorage.SaveAsync(_storage.OutputContainer, path, content, output.ContentType, cancellationToken);

                dbContext.OutputArtifacts.Add(new OutputArtifact
                {
                    GenerationRunId = run.Id,
                    ClientId = run.ClientId,
                    FilingPeriodId = run.FilingPeriodId,
                    ArtifactKind = "CSV",
                    FileName = output.FileName,
                    ContentType = output.ContentType,
                    SizeBytes = size,
                    StorageProvider = stored.Provider,
                    StorageContainer = stored.Container,
                    StoragePath = stored.Path,
                });
            }

            run.Status = GenerationRunStatus.Completed;
            run.CompletedAtUtc = DateTime.UtcNow;
            run.ErrorMessage = null;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Falló la generación {RunId}.", run.Id);
            Fail(run, ex.Message);
        }

        await dbContext.SaveChangesAsync(cancellationToken);
    }

    private static void Fail(GenerationRun run, string message)
    {
        run.Status = GenerationRunStatus.Failed;
        run.CompletedAtUtc = DateTime.UtcNow;
        run.ErrorMessage = message.Length > 2000 ? message[..2000] : message;
    }
}
```

- [ ] **Step 5: Worker**

Create `apps/api/Accounting.Api/Features/Generation/GenerationWorker.cs`:

```csharp
using Microsoft.Extensions.Options;

namespace Accounting.Api.Features.Generation;

public sealed class GenerationWorker(
    IServiceScopeFactory scopeFactory,
    IOptions<GenerationOptions> options,
    ILogger<GenerationWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var pollInterval = TimeSpan.FromSeconds(options.Value.PollIntervalSeconds);
        logger.LogInformation("GenerationWorker iniciado. Intervalo: {Interval}s.", pollInterval.TotalSeconds);

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                using var scope = scopeFactory.CreateScope();
                var processor = scope.ServiceProvider.GetRequiredService<GenerationRunProcessor>();

                await processor.RecoverStuckRunsAsync(stoppingToken);

                var runId = await processor.TryClaimAsync(stoppingToken);
                if (runId is null)
                {
                    await Task.Delay(pollInterval, stoppingToken);
                    continue;
                }

                await processor.ProcessAsync(runId.Value, stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "Error inesperado en GenerationWorker.");
                await Task.Delay(TimeSpan.FromSeconds(5), stoppingToken);
            }
        }
    }
}
```

- [ ] **Step 6: Register everything in Program.cs**

In `Program.cs`, after the `builder.Services.Configure<StorageOptions>(...)` line, add:

```csharp
builder.Services.AddOptions<Accounting.Api.Features.Generation.GenerationOptions>()
    .Bind(builder.Configuration.GetSection(Accounting.Api.Features.Generation.GenerationOptions.SectionName))
    .ValidateDataAnnotations()
    .ValidateOnStart();
```

After `builder.Services.AddScoped<Accounting.Api.Features.Generation.GenerationRunsService>();` add:

```csharp
builder.Services.AddScoped<Accounting.Api.Features.Generation.GenerationRunProcessor>();
builder.Services.AddSingleton<Accounting.Api.Features.Generation.ICsvGenerator, Accounting.Api.Features.Generation.PlaceholderCsvGenerator>();
builder.Services.AddHostedService<Accounting.Api.Features.Generation.GenerationWorker>();
```

Add to `appsettings.json` after the `"Features"` object:

```json
  "Generation": {
    "PollIntervalSeconds": 3,
    "RunTimeoutMinutes": 10
  },
```

- [ ] **Step 7: Run the tests**

Run: `dotnet test apps/api/Accounting.slnx`
Expected: all pass, including 6 `GenerationProcessorTests`. The `ApiFactory` removes `GenerationWorker` because its namespace starts with `Accounting.Api`, so processing only happens when a test calls the processor.

- [ ] **Step 8: Commit**

```bash
git add -A apps/api
git commit -m "feat(api): generation worker with atomic claim, stuck-run recovery, placeholder CSV

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Remove startup migrate, add ProblemDetails handler, update docs

**Files:**
- Modify: `apps/api/Accounting.Api/Program.cs`
- Modify: `README.md`
- Test: `apps/api/Accounting.Api.Tests/SmokeTests.cs` (one added test)

**Interfaces:**
- Consumes: nothing new.
- Produces: unhandled exceptions return `application/problem+json` with status 500 and no exception detail outside Development.

- [ ] **Step 1: Write the failing test**

Add to `SmokeTests.cs` inside the class:

```csharp
    [Fact]
    public async Task Unknown_route_under_api_returns_problem_details_shape_for_404()
    {
        var client = await fixture.Factory.RegisterAndLoginAsync();
        var response = await client.GetAsync($"/api/clients/{Guid.NewGuid()}");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
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
```

- [ ] **Step 2: Run to verify the migrate test fails**

Run: `dotnet test apps/api/Accounting.slnx --filter FullyQualifiedName~SmokeTests`
Expected: `Startup_does_not_run_migrations` FAILS because `Program.cs` still contains `db.Database.Migrate()`.

- [ ] **Step 3: Edit Program.cs**

Remove this block entirely:

```csharp
using (var scope = app.Services.CreateScope())
{
    var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
    db.Database.Migrate();
}
```

Before `var app = builder.Build();` add:

```csharp
builder.Services.AddProblemDetails();
```

Immediately after `var app = builder.Build();` add:

```csharp
app.UseExceptionHandler();
app.UseStatusCodePages();
```

`AddProblemDetails` plus `UseExceptionHandler()` with no arguments makes ASP.NET Core write an RFC 7807 body for unhandled exceptions. In Development the developer exception page still applies because `WebApplication` adds it automatically before this middleware; in Production the body contains only `type`, `title`, `status`, and `traceId`.

If `using Accounting.Api.Data;` or `using Microsoft.EntityFrameworkCore;` is now unused in `Program.cs`, leave `Microsoft.EntityFrameworkCore` (needed by `UseNpgsql`) and remove `Accounting.Api.Data` only if the compiler flags it unused. Unused usings are warnings, not errors, so either way the build passes.

- [ ] **Step 4: Update the README**

In `README.md`, in the "Levantar proyecto local" API step, replace:

```bash
# La migración ya existe; al iniciar, la API aplica migrations automáticamente
dotnet run
```

with:

```bash
# Aplicar migraciones (la API ya no las aplica al iniciar)
dotnet ef database update
dotnet run
```

In the "Migraciones EF Core" section, replace the `export PATH=...` line with:

```bash
# dotnet-ef está instalado como herramienta local (apps/api/.config/dotnet-tools.json)
dotnet tool restore
```

- [ ] **Step 5: Run the full suite**

Run: `dotnet test apps/api/Accounting.slnx`
Expected: all tests pass.

- [ ] **Step 6: Run the API locally once to confirm boot without a migrate call**

```bash
docker compose up -d
cd apps/api/Accounting.Api && dotnet ef database update && timeout 15 dotnet run || true; cd ../../..
```

Expected: `dotnet ef database update` applies `GenerationRuns`. `dotnet run` logs `GenerationWorker iniciado` and listens on port 5184 until the timeout kills it. If `timeout` is missing on macOS, run `dotnet run` and stop it with Ctrl+C after seeing the log line.

- [ ] **Step 7: Commit**

```bash
git add apps/api/Accounting.Api/Program.cs apps/api/Accounting.Api.Tests/SmokeTests.cs README.md
git commit -m "feat(api): remove startup migrate, add ProblemDetails handler

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Final verification

**Files:** none created.

- [ ] **Step 1: Clean build with warnings visible**

Run: `dotnet build apps/api/Accounting.slnx -warnaserror`
Expected: succeeds. If it fails on a warning introduced by this work (unused using, nullable), fix it. If it fails on a pre-existing warning outside `Features/`, `Domain/`, `Data/AppDbContext.cs`, or the test project, run without `-warnaserror` and note the warning in the final report instead of fixing unrelated code.

- [ ] **Step 2: Full test run**

Run: `dotnet test apps/api/Accounting.slnx`
Expected: 23 tests pass (4 smoke, 2 migration, 5 uploads, 6 runs, 6 processor).

- [ ] **Step 3: Confirm no leftovers**

```bash
grep -rn "ParseJob\|ParsePipelineWorker\|DTOs.Uploads" apps/api --include=*.cs | grep -v "/Migrations/"
```

Expected: no output. Migration files may still mention `parse_jobs` because they drop it.

- [ ] **Step 4: Report**

Summarize for the user: endpoints added and removed, the web contract changes (`jobs` removed from uploads, `includedInLatestRun` added, new `/runs` routes, statuses are strings), and that production requires the delivery pipeline change before deploying because migrations no longer auto-apply.
