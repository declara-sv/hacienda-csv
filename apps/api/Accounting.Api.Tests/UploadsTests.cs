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
