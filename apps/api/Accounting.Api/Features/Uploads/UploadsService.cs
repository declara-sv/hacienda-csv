using Accounting.Api.Data;
using Accounting.Api.Domain.Entities;
using Accounting.Api.Domain.Enums;
using Accounting.Api.Storage;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
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
    IOptions<StorageOptions> storageOptions,
    ILogger<UploadsService> logger)
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

        dbContext.Uploads.Remove(upload);
        await dbContext.SaveChangesAsync(cancellationToken);

        try
        {
            await fileStorage.DeleteAsync(new StoredFileReference(upload.StorageProvider, upload.StorageContainer, upload.StoragePath), cancellationToken);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "No se pudo eliminar el archivo de almacenamiento para el upload {UploadId}.", upload.Id);
        }

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
