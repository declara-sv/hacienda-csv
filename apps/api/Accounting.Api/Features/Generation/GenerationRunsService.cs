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
            .ThenByDescending(a => a.Id)
            .Select(a => new OutputArtifactDto(a.Id, a.ArtifactKind, a.FileName, a.CreatedAtUtc, a.SizeBytes))
            .ToList());
}
