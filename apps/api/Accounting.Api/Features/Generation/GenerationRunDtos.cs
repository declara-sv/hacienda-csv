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
