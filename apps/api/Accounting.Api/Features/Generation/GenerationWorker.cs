using Microsoft.Extensions.Options;

namespace Accounting.Api.Features.Generation;

public sealed class GenerationWorker(
    IServiceScopeFactory scopeFactory,
    IOptions<GenerationOptions> options,
    ILogger<GenerationWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var pollInterval = TimeSpan.FromSeconds(options.Value.PollIntervalSeconds);
        logger.LogInformation("GenerationWorker iniciado. Intervalo: {Interval}s.", pollInterval.TotalSeconds);

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                using var scope = scopeFactory.CreateScope();
                var processor = scope.ServiceProvider.GetRequiredService<GenerationRunProcessor>();

                await processor.RecoverStuckRunsAsync(stoppingToken);

                var runId = await processor.TryClaimAsync(stoppingToken);
                if (runId is null)
                {
                    await Task.Delay(pollInterval, stoppingToken);
                    continue;
                }

                await processor.ProcessAsync(runId.Value, stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "Error inesperado en GenerationWorker.");
                await Task.Delay(TimeSpan.FromSeconds(5), stoppingToken);
            }
        }
    }
}
