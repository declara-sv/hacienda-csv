using Accounting.Api.Domain.Enums;

namespace Accounting.Api.Domain.Entities;

public sealed class GenerationRun
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid ClientId { get; set; }
    public Guid FilingPeriodId { get; set; }
    public Guid RequestedByUserId { get; set; }
    public int Version { get; set; }
    public GenerationRunStatus Status { get; set; } = GenerationRunStatus.Pending;
    public string? ErrorMessage { get; set; }
    public DateTime CreatedAtUtc { get; set; } = DateTime.UtcNow;
    public DateTime? StartedAtUtc { get; set; }
    public DateTime? CompletedAtUtc { get; set; }

    public Client Client { get; set; } = null!;
    public FilingPeriod FilingPeriod { get; set; } = null!;
    public AppUser RequestedByUser { get; set; } = null!;
    public ICollection<GenerationRunFile> Files { get; set; } = new List<GenerationRunFile>();
    public ICollection<OutputArtifact> OutputArtifacts { get; set; } = new List<OutputArtifact>();
}
