namespace Accounting.Api.Domain.Entities;

public sealed class FilingPeriod
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid ClientId { get; set; }
    public int Year { get; set; }
    public int Month { get; set; }
    public DateTime CreatedAtUtc { get; set; } = DateTime.UtcNow;

    public Client Client { get; set; } = null!;
    public ICollection<Upload> Uploads { get; set; } = new List<Upload>();
    public ICollection<OutputArtifact> OutputArtifacts { get; set; } = new List<OutputArtifact>();
}
