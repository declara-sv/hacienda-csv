using System.ComponentModel.DataAnnotations;

namespace Accounting.Api.Features.Generation;

public sealed class GenerationOptions
{
    public const string SectionName = "Generation";

    [Range(1, 300)]
    public int PollIntervalSeconds { get; set; } = 3;

    [Range(1, 1440)]
    public int RunTimeoutMinutes { get; set; } = 10;
}
