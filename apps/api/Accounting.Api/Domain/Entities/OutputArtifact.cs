namespace Accounting.Api.Domain.Entities;

public sealed class OutputArtifact
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid ParseJobId { get; set; }
    public Guid ClientId { get; set; }
    public Guid FilingPeriodId { get; set; }

    public string ArtifactKind { get; set; } = "CSV";
    public string FileName { get; set; } = string.Empty;
    public string ContentType { get; set; } = "text/csv";
    public long SizeBytes { get; set; }

    public string StorageProvider { get; set; } = string.Empty;
    public string StorageContainer { get; set; } = string.Empty;
    public string StoragePath { get; set; } = string.Empty;
    public DateTime CreatedAtUtc { get; set; } = DateTime.UtcNow;

    public ParseJob ParseJob { get; set; } = null!;
    public Client Client { get; set; } = null!;
    public FilingPeriod FilingPeriod { get; set; } = null!;
}
