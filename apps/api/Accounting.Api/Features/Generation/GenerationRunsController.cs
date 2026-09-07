using Accounting.Api.Auth;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Accounting.Api.Features.Generation;

[ApiController]
[Authorize]
[Route("api/clients/{clientId:guid}/periods/{filingPeriodId:guid}/runs")]
public sealed class GenerationRunsController(
    GenerationRunsService runsService,
    ICurrentUserService currentUserService) : ControllerBase
{
    [HttpPost]
    [ProducesResponseType<GenerationRunDto>(StatusCodes.Status202Accepted)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    public async Task<IActionResult> Create(Guid clientId, Guid filingPeriodId, CancellationToken cancellationToken)
    {
        var result = await runsService.CreateAsync(clientId, filingPeriodId, currentUserService.UserId!.Value, cancellationToken);

        return result.Outcome switch
        {
            CreateRunOutcome.Created => Accepted($"/api/clients/{clientId}/periods/{filingPeriodId}/runs/{result.Run!.Id}", result.Run),
            CreateRunOutcome.NoUploads => BadRequest(new ValidationProblemDetails(new Dictionary<string, string[]>
            {
                ["uploads"] = ["El período no tiene archivos para generar."],
            })),
            CreateRunOutcome.ActiveRunExists => Conflict(new ProblemDetails
            {
                Title = "Ya existe una generación en curso para este período.",
                Status = StatusCodes.Status409Conflict,
            }),
            _ => NotFound(),
        };
    }

    [HttpGet]
    [ProducesResponseType<IReadOnlyList<GenerationRunDto>>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> List(Guid clientId, Guid filingPeriodId, CancellationToken cancellationToken)
    {
        var runs = await runsService.ListAsync(clientId, filingPeriodId, currentUserService.UserId!.Value, cancellationToken);
        return runs is null ? NotFound() : Ok(runs);
    }

    [HttpGet("{runId:guid}")]
    [ProducesResponseType<GenerationRunDto>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Get(Guid clientId, Guid filingPeriodId, Guid runId, CancellationToken cancellationToken)
    {
        var run = await runsService.GetAsync(clientId, filingPeriodId, runId, currentUserService.UserId!.Value, cancellationToken);
        return run is null ? NotFound() : Ok(run);
    }
}
