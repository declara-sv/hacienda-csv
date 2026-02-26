using System.ComponentModel.DataAnnotations;

namespace Accounting.Api.DTOs.Clients;

public sealed class CreateClientRequestDto
{
    [Required, MaxLength(160)]
    public string Name { get; init; } = string.Empty;

    [Required, MaxLength(32)]
    public string TaxId { get; init; } = string.Empty;

    [MaxLength(2000)]
    public string? Notes { get; init; }
}

public sealed class UpdateClientRequestDto
{
    [Required, MaxLength(160)]
    public string Name { get; init; } = string.Empty;

    [Required, MaxLength(32)]
    public string TaxId { get; init; } = string.Empty;

    [MaxLength(2000)]
    public string? Notes { get; init; }
}

public sealed record ClientSummaryDto(
    Guid Id,
    string Name,
    string TaxId,
    int FilingPeriodsCount,
    DateTime CreatedAtUtc);

public sealed record ClientConfigDto(
    Guid Id,
    string Name,
    string PrefillValuesJson,
    string? TransformationRulesJson,
    bool IsActive,
    DateTime UpdatedAtUtc);

public sealed record FilingPeriodSummaryDto(
    Guid Id,
    int Year,
    int Month,
    DateTime CreatedAtUtc);

public sealed record ClientDetailDto(
    Guid Id,
    string Name,
    string TaxId,
    string? Notes,
    DateTime CreatedAtUtc,
    IReadOnlyList<ClientConfigDto> Configurations,
    IReadOnlyList<FilingPeriodSummaryDto> FilingPeriods);

public sealed class CreateClientConfigRequestDto
{
    [Required, MaxLength(80)]
    public string Name { get; init; } = string.Empty;

    [Required]
    public string PrefillValuesJson { get; init; } = "{}";

    public string? TransformationRulesJson { get; init; }
    public bool IsActive { get; init; }
}

public sealed class UpdateClientConfigRequestDto
{
    [Required, MaxLength(80)]
    public string Name { get; init; } = string.Empty;

    [Required]
    public string PrefillValuesJson { get; init; } = "{}";

    public string? TransformationRulesJson { get; init; }
    public bool IsActive { get; init; }
}
