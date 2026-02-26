using Accounting.Api.Auth;
using Accounting.Api.Data;
using Accounting.Api.Domain.Entities;
using Accounting.Api.DTOs.Uploads;
using Accounting.Api.Storage;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace Accounting.Api.Controllers;

[ApiController]
[Authorize]
[Route("api/clients/{clientId:guid}/periods/{filingPeriodId:guid}/uploads")]
public sealed class UploadsController(
    AppDbContext dbContext,
    ICurrentUserService currentUserService,
    IFileStorage fileStorage,
    IOptions<StorageOptions> storageOptions) : ControllerBase
{
    private readonly StorageOptions _storageOptions = storageOptions.Value;

    [HttpGet]
    [ProducesResponseType<IReadOnlyList<UploadDto>>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> List(Guid clientId, Guid filingPeriodId, CancellationToken cancellationToken)
    {
        var userId = currentUserService.UserId!.Value;

        var period = await dbContext.FindOwnedFilingPeriodAsync(clientId, filingPeriodId, userId, cancellationToken);
        if (period is null)
        {
            return NotFound();
        }

        var uploads = await dbContext.Uploads
            .Where(x => x.ClientId == clientId && x.FilingPeriodId == filingPeriodId)
            .OrderByDescending(x => x.CreatedAtUtc)
            .Select(x => new UploadDto(
                x.Id,
                x.FilingPeriodId,
                x.OriginalFileName,
                x.SourceFileKind,
                x.ContentType,
                x.SizeBytes,
                x.CreatedAtUtc,
                x.ParseJobs
                    .OrderByDescending(j => j.CreatedAtUtc)
                    .Select(j => new ParseJobDto(
                        j.Id,
                        j.Status,
                        j.ErrorMessage,
                        j.CreatedAtUtc,
                        j.StartedAtUtc,
                        j.CompletedAtUtc,
                        j.OutputArtifacts
                            .OrderByDescending(a => a.CreatedAtUtc)
                            .Select(a => new OutputArtifactDto(a.Id, a.ArtifactKind, a.FileName, a.CreatedAtUtc, a.SizeBytes))
                            .ToList()))
                    .ToList()))
            .ToListAsync(cancellationToken);

        return Ok(uploads);
    }

    [HttpPost]
    [RequestSizeLimit(20_000_000)]
    [ProducesResponseType<UploadCreatedDto>(StatusCodes.Status201Created)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Upload(Guid clientId, Guid filingPeriodId, [FromForm] CreateUploadRequestDto request, CancellationToken cancellationToken)
    {
        var userId = currentUserService.UserId!.Value;
        var period = await dbContext.FindOwnedFilingPeriodAsync(clientId, filingPeriodId, userId, cancellationToken);
        if (period is null)
        {
            return NotFound();
        }

        if (request.File.Length <= 0)
        {
            return BadRequest(new ValidationProblemDetails(new Dictionary<string, string[]>
            {
                ["file"] = ["El archivo está vacío."],
            }));
        }

        if (!IsValidFileType(request.File.FileName, request.SourceFileKind))
        {
            return BadRequest(new ValidationProblemDetails(new Dictionary<string, string[]>
            {
                ["file"] = ["El tipo de archivo no corresponde al tipo seleccionado (Excel/PDF)."],
            }));
        }

        var extension = Path.GetExtension(request.File.FileName).ToLowerInvariant();
        var safeFileName = SanitizeFileName(Path.GetFileNameWithoutExtension(request.File.FileName));
        var fileName = $"{safeFileName}{extension}";

        var path = $"{clientId}/{period.Year:D4}/{period.Month:D2}/{Guid.NewGuid()}_{fileName}";

        await using var stream = request.File.OpenReadStream();
        var stored = await fileStorage.SaveAsync(
            _storageOptions.UploadContainer,
            path,
            stream,
            request.File.ContentType,
            cancellationToken);

        var upload = new Upload
        {
            ClientId = clientId,
            FilingPeriodId = filingPeriodId,
            UploadedByUserId = userId,
            OriginalFileName = request.File.FileName,
            ContentType = request.File.ContentType,
            SourceFileKind = request.SourceFileKind,
            SizeBytes = request.File.Length,
            StorageProvider = stored.Provider,
            StorageContainer = stored.Container,
            StoragePath = stored.Path,
        };

        var parseJob = new ParseJob
        {
            UploadId = upload.Id,
        };

        dbContext.Uploads.Add(upload);
        dbContext.ParseJobs.Add(parseJob);
        await dbContext.SaveChangesAsync(cancellationToken);

        return Created($"/api/clients/{clientId}/periods/{filingPeriodId}/uploads/{upload.Id}", new UploadCreatedDto(upload.Id, parseJob.Id, parseJob.Status));
    }

    private static string SanitizeFileName(string fileName)
    {
        var invalidChars = Path.GetInvalidFileNameChars();
        var cleaned = new string(fileName.Select(c => invalidChars.Contains(c) ? '_' : c).ToArray());
        return string.IsNullOrWhiteSpace(cleaned) ? "archivo" : cleaned;
    }

    private static bool IsValidFileType(string fileName, string sourceFileKind)
    {
        var extension = Path.GetExtension(fileName).ToLowerInvariant();

        return sourceFileKind switch
        {
            "Excel" => extension is ".xls" or ".xlsx",
            "PDF" => extension == ".pdf",
            _ => false,
        };
    }
}
