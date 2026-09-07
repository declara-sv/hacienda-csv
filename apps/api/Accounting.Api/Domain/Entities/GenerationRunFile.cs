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
