namespace Accounting.Api.Domain.Entities;

public sealed class Client
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid OwnerUserId { get; set; }
    public string Name { get; set; } = string.Empty;
    public string TaxId { get; set; } = string.Empty;
    public string? Notes { get; set; }
    public DateTime CreatedAtUtc { get; set; } = DateTime.UtcNow;

    public AppUser OwnerUser { get; set; } = null!;
    public ICollection<ClientConfig> Configurations { get; set; } = new List<ClientConfig>();
    public ICollection<FilingPeriod> FilingPeriods { get; set; } = new List<FilingPeriod>();
    public ICollection<Upload> Uploads { get; set; } = new List<Upload>();
}
