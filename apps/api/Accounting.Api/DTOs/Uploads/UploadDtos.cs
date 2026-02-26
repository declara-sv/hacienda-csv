using Accounting.Api.Domain.Enums;
using System.ComponentModel.DataAnnotations;

namespace Accounting.Api.DTOs.Uploads;

public sealed class CreateUploadRequestDto
{
    [Required]
    public IFormFile File { get; init; } = null!;

    [Required]
    [RegularExpression("^(Excel|PDF)$", ErrorMessage = "El tipo debe ser Excel o PDF.")]
    public string SourceFileKind { get; init; } = string.Empty;
}

public sealed record OutputArtifactDto(
    Guid Id,
    string ArtifactKind,
    string FileName,
    DateTime CreatedAtUtc,
    long SizeBytes);

public sealed record ParseJobDto(
    Guid Id,
    ParseJobStatus Status,
    string? ErrorMessage,
    DateTime CreatedAtUtc,
    DateTime? StartedAtUtc,
    DateTime? CompletedAtUtc,
    IReadOnlyList<OutputArtifactDto> Artifacts);

public sealed record UploadDto(
    Guid Id,
    Guid FilingPeriodId,
    string OriginalFileName,
    string SourceFileKind,
    string ContentType,
    long SizeBytes,
    DateTime CreatedAtUtc,
    IReadOnlyList<ParseJobDto> Jobs);

public sealed record UploadCreatedDto(Guid UploadId, Guid ParseJobId, ParseJobStatus Status);
