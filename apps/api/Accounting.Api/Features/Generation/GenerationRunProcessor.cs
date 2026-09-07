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
                Stream? probe;
                try
                {
                    probe = await fileStorage.OpenReadAsync(reference, cancellationToken);
                }
                catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
                {
                    throw;
                }
                catch (Exception ex)
                {
                    var message = $"Error al leer el archivo: {ex.Message}";
                    file.Status = GenerationRunFileStatus.Failed;
                    file.ErrorMessage = message.Length > 2000 ? message[..2000] : message;
                    continue;
                }

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
