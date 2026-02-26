using Accounting.Api.Domain.Enums;

namespace Accounting.Api.Domain.Entities;

public sealed class ParseJob
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid UploadId { get; set; }
    public ParseJobStatus Status { get; set; } = ParseJobStatus.Pending;
    public string? ErrorMessage { get; set; }
    public DateTime CreatedAtUtc { get; set; } = DateTime.UtcNow;
    public DateTime? StartedAtUtc { get; set; }
    public DateTime? CompletedAtUtc { get; set; }

    public Upload Upload { get; set; } = null!;
    public ICollection<OutputArtifact> OutputArtifacts { get; set; } = new List<OutputArtifact>();
}
