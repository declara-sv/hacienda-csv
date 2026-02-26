using System.Text;
using Accounting.Api.Data;
using Accounting.Api.Domain.Entities;
using Accounting.Api.Domain.Enums;
using Accounting.Api.Storage;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace Accounting.Api.Workers;

public sealed class ParsePipelineWorker(
    IServiceScopeFactory serviceScopeFactory,
    ILogger<ParsePipelineWorker> logger,
    IFileStorage fileStorage,
    IOptions<StorageOptions> storageOptions) : BackgroundService
{
    private readonly StorageOptions _storageOptions = storageOptions.Value;

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        logger.LogInformation("ParsePipelineWorker iniciado.");

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                using var scope = serviceScopeFactory.CreateScope();
                var dbContext = scope.ServiceProvider.GetRequiredService<AppDbContext>();

                var job = await dbContext.ParseJobs
                    .Include(x => x.Upload)
                    .ThenInclude(x => x.FilingPeriod)
                    .OrderBy(x => x.CreatedAtUtc)
                    .FirstOrDefaultAsync(
                        x => x.Status == ParseJobStatus.Pending,
                        stoppingToken);

                if (job is null)
                {
                    await Task.Delay(TimeSpan.FromSeconds(3), stoppingToken);
                    continue;
                }

                job.Status = ParseJobStatus.Running;
                job.StartedAtUtc = DateTime.UtcNow;
                await dbContext.SaveChangesAsync(stoppingToken);

                await ProcessJobAsync(job, dbContext, stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "Error inesperado en ParsePipelineWorker");
                await Task.Delay(TimeSpan.FromSeconds(5), stoppingToken);
            }
        }
    }

    private async Task ProcessJobAsync(ParseJob job, AppDbContext dbContext, CancellationToken cancellationToken)
    {
        try
        {
            var upload = job.Upload;
            var period = upload.FilingPeriod;

            var csv = BuildDummyCsv(upload.ClientId, period.Year, period.Month, upload.OriginalFileName);
            var bytes = Encoding.UTF8.GetBytes(csv);

            await using var stream = new MemoryStream(bytes);
            var outputPath = $"{upload.ClientId}/{period.Year:D4}/{period.Month:D2}/{job.Id}.csv";
            var stored = await fileStorage.SaveAsync(
                _storageOptions.OutputContainer,
                outputPath,
                stream,
                "text/csv",
                cancellationToken);

            var artifact = new OutputArtifact
            {
                ParseJobId = job.Id,
                ClientId = upload.ClientId,
                FilingPeriodId = upload.FilingPeriodId,
                ArtifactKind = "CSV",
                FileName = $"resultado_{period.Year:D4}_{period.Month:D2}_{job.Id}.csv",
                ContentType = "text/csv",
                SizeBytes = bytes.LongLength,
                StorageProvider = stored.Provider,
                StorageContainer = stored.Container,
                StoragePath = stored.Path,
            };

            dbContext.OutputArtifacts.Add(artifact);

            job.Status = ParseJobStatus.Completed;
            job.CompletedAtUtc = DateTime.UtcNow;
            job.ErrorMessage = null;

            await dbContext.SaveChangesAsync(cancellationToken);
        }
        catch (Exception ex)
        {
            job.Status = ParseJobStatus.Failed;
            job.CompletedAtUtc = DateTime.UtcNow;
            job.ErrorMessage = $"Error en pipeline placeholder: {ex.Message}";
            await dbContext.SaveChangesAsync(cancellationToken);
        }
    }

    private static string BuildDummyCsv(Guid clientId, int year, int month, string sourceName)
    {
        var builder = new StringBuilder();
        builder.AppendLine("cliente_id,anio,mes,archivo_origen,estado,mensaje");
        builder.AppendLine($"{clientId},{year},{month},\"{sourceName}\",COMPLETADO,\"CSV generado por placeholder\"");
        return builder.ToString();
    }
}
