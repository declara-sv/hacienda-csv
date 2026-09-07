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
