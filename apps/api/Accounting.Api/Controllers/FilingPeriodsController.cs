using Accounting.Api.Auth;
using Accounting.Api.Data;
using Accounting.Api.Domain.Entities;
using Accounting.Api.DTOs.FilingPeriods;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Accounting.Api.Controllers;

[ApiController]
[Authorize]
[Route("api/clients/{clientId:guid}/periods")]
public sealed class FilingPeriodsController(AppDbContext dbContext, ICurrentUserService currentUserService) : ControllerBase
{
    [HttpGet]
    [ProducesResponseType<IReadOnlyList<FilingPeriodDto>>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> List(Guid clientId, CancellationToken cancellationToken)
    {
        var userId = currentUserService.UserId!.Value;
        var ownsClient = await dbContext.Clients.AnyAsync(x => x.Id == clientId && x.OwnerUserId == userId, cancellationToken);
        if (!ownsClient)
        {
            return NotFound();
        }

        var periods = await dbContext.FilingPeriods
            .Where(x => x.ClientId == clientId)
            .OrderByDescending(x => x.Year)
            .ThenByDescending(x => x.Month)
            .Select(x => new FilingPeriodDto(x.Id, x.Year, x.Month, x.CreatedAtUtc, x.Uploads.Count))
            .ToListAsync(cancellationToken);

        return Ok(periods);
    }

    [HttpPost]
    [ProducesResponseType<FilingPeriodDto>(StatusCodes.Status201Created)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Create(Guid clientId, CreateFilingPeriodRequestDto request, CancellationToken cancellationToken)
    {
        var userId = currentUserService.UserId!.Value;
        var client = await dbContext.FindOwnedClientAsync(clientId, userId, cancellationToken);
        if (client is null)
        {
            return NotFound();
        }

        var exists = await dbContext.FilingPeriods.AnyAsync(
            x => x.ClientId == clientId && x.Year == request.Year && x.Month == request.Month,
            cancellationToken);

        if (exists)
        {
            return BadRequest(new ValidationProblemDetails(new Dictionary<string, string[]>
            {
                ["period"] = ["El período ya existe para este cliente."],
            }));
        }

        var period = new FilingPeriod
        {
            ClientId = clientId,
            Year = request.Year,
            Month = request.Month,
        };

        dbContext.FilingPeriods.Add(period);
        await dbContext.SaveChangesAsync(cancellationToken);

        return Created($"/api/clients/{clientId}/periods/{period.Id}", new FilingPeriodDto(period.Id, period.Year, period.Month, period.CreatedAtUtc, 0));
    }

    [HttpPut("{periodId:guid}")]
    [ProducesResponseType<FilingPeriodDto>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Update(Guid clientId, Guid periodId, UpdateFilingPeriodRequestDto request, CancellationToken cancellationToken)
    {
        var userId = currentUserService.UserId!.Value;
        var ownsClient = await dbContext.Clients.AnyAsync(x => x.Id == clientId && x.OwnerUserId == userId, cancellationToken);
        if (!ownsClient)
        {
            return NotFound();
        }

        var period = await dbContext.FilingPeriods.FirstOrDefaultAsync(x => x.Id == periodId && x.ClientId == clientId, cancellationToken);
        if (period is null)
        {
            return NotFound();
        }

        var duplicate = await dbContext.FilingPeriods.AnyAsync(
            x => x.ClientId == clientId && x.Id != periodId && x.Year == request.Year && x.Month == request.Month,
            cancellationToken);

        if (duplicate)
        {
            return BadRequest(new ValidationProblemDetails(new Dictionary<string, string[]>
            {
                ["period"] = ["Ya existe otro período con ese año y mes."],
            }));
        }

        period.Year = request.Year;
        period.Month = request.Month;
        await dbContext.SaveChangesAsync(cancellationToken);

        var uploadsCount = await dbContext.Uploads.CountAsync(x => x.FilingPeriodId == periodId, cancellationToken);
        return Ok(new FilingPeriodDto(period.Id, period.Year, period.Month, period.CreatedAtUtc, uploadsCount));
    }

    [HttpDelete("{periodId:guid}")]
    [ProducesResponseType(StatusCodes.Status204NoContent)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Delete(Guid clientId, Guid periodId, CancellationToken cancellationToken)
    {
        var userId = currentUserService.UserId!.Value;
        var ownsClient = await dbContext.Clients.AnyAsync(x => x.Id == clientId && x.OwnerUserId == userId, cancellationToken);
        if (!ownsClient)
        {
            return NotFound();
        }

        var period = await dbContext.FilingPeriods.FirstOrDefaultAsync(x => x.Id == periodId && x.ClientId == clientId, cancellationToken);
        if (period is null)
        {
            return NotFound();
        }

        dbContext.FilingPeriods.Remove(period);
        await dbContext.SaveChangesAsync(cancellationToken);

        return NoContent();
    }
}
