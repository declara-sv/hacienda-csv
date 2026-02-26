namespace Accounting.Api.Domain.Entities;

public sealed class ClientConfig
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid ClientId { get; set; }
    public string Name { get; set; } = "Base";
    public string PrefillValuesJson { get; set; } = "{}";
    public string? TransformationRulesJson { get; set; }
    public bool IsActive { get; set; } = true;
    public DateTime CreatedAtUtc { get; set; } = DateTime.UtcNow;
    public DateTime UpdatedAtUtc { get; set; } = DateTime.UtcNow;

    public Client Client { get; set; } = null!;
}
