using System.ComponentModel.DataAnnotations;

namespace Accounting.Api.DTOs.FilingPeriods;

public sealed class CreateFilingPeriodRequestDto
{
    [Range(2000, 2100)]
    public int Year { get; init; }

    [Range(1, 12)]
    public int Month { get; init; }
}

public sealed class UpdateFilingPeriodRequestDto
{
    [Range(2000, 2100)]
    public int Year { get; init; }

    [Range(1, 12)]
    public int Month { get; init; }
}

public sealed record FilingPeriodDto(
    Guid Id,
    int Year,
    int Month,
    DateTime CreatedAtUtc,
    int UploadsCount);
