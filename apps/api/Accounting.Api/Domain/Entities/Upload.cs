namespace Accounting.Api.Domain.Entities;

public sealed class Upload
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid ClientId { get; set; }
    public Guid FilingPeriodId { get; set; }
    public Guid UploadedByUserId { get; set; }

    public string OriginalFileName { get; set; } = string.Empty;
    public string ContentType { get; set; } = "application/octet-stream";
    public string SourceFileKind { get; set; } = string.Empty;
    public long SizeBytes { get; set; }

    public string StorageProvider { get; set; } = string.Empty;
    public string StorageContainer { get; set; } = string.Empty;
    public string StoragePath { get; set; } = string.Empty;
    public DateTime CreatedAtUtc { get; set; } = DateTime.UtcNow;

    public Client Client { get; set; } = null!;
    public FilingPeriod FilingPeriod { get; set; } = null!;
    public AppUser UploadedByUser { get; set; } = null!;
    public ICollection<ParseJob> ParseJobs { get; set; } = new List<ParseJob>();
}
