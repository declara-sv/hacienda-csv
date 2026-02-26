using Accounting.Api.Auth;
using Accounting.Api.Data;
using Accounting.Api.Domain.Entities;
using Accounting.Api.DTOs.Clients;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Accounting.Api.Controllers;

[ApiController]
[Authorize]
[Route("api/clients")]
public sealed class ClientsController(AppDbContext dbContext, ICurrentUserService currentUserService) : ControllerBase
{
    [HttpGet]
    [ProducesResponseType<IReadOnlyList<ClientSummaryDto>>(StatusCodes.Status200OK)]
    public async Task<IActionResult> List(CancellationToken cancellationToken)
    {
        var userId = currentUserService.UserId!.Value;

        var clients = await dbContext.Clients
            .Where(x => x.OwnerUserId == userId)
            .OrderBy(x => x.Name)
            .Select(x => new ClientSummaryDto(
                x.Id,
                x.Name,
                x.TaxId,
                x.FilingPeriods.Count,
                x.CreatedAtUtc))
            .ToListAsync(cancellationToken);

        return Ok(clients);
    }

    [HttpPost]
    [ProducesResponseType<ClientDetailDto>(StatusCodes.Status201Created)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public async Task<IActionResult> Create(CreateClientRequestDto request, CancellationToken cancellationToken)
    {
        var userId = currentUserService.UserId!.Value;

        var client = new Client
        {
            OwnerUserId = userId,
            Name = request.Name.Trim(),
            TaxId = request.TaxId.Trim(),
            Notes = request.Notes?.Trim(),
        };

        dbContext.Clients.Add(client);
        var defaultConfig = new ClientConfig
        {
            ClientId = client.Id,
            Name = "Base",
            PrefillValuesJson = "{}",
            IsActive = true,
        };
        dbContext.ClientConfigs.Add(defaultConfig);

        await dbContext.SaveChangesAsync(cancellationToken);

        return CreatedAtAction(nameof(GetById), new { clientId = client.Id }, new ClientDetailDto(
            client.Id,
            client.Name,
            client.TaxId,
            client.Notes,
            client.CreatedAtUtc,
            [new ClientConfigDto(defaultConfig.Id, defaultConfig.Name, defaultConfig.PrefillValuesJson, defaultConfig.TransformationRulesJson, defaultConfig.IsActive, defaultConfig.UpdatedAtUtc)],
            []));
    }

    [HttpGet("{clientId:guid}")]
    [ProducesResponseType<ClientDetailDto>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> GetById(Guid clientId, CancellationToken cancellationToken)
    {
        var userId = currentUserService.UserId!.Value;

        var client = await dbContext.Clients
            .Include(x => x.Configurations)
            .Include(x => x.FilingPeriods)
            .FirstOrDefaultAsync(x => x.Id == clientId && x.OwnerUserId == userId, cancellationToken);

        if (client is null)
        {
            return NotFound();
        }

        return Ok(ToDetailDto(client));
    }

    [HttpPut("{clientId:guid}")]
    [ProducesResponseType<ClientDetailDto>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Update(Guid clientId, UpdateClientRequestDto request, CancellationToken cancellationToken)
    {
        var userId = currentUserService.UserId!.Value;
        var client = await dbContext.FindOwnedClientAsync(clientId, userId, cancellationToken);
        if (client is null)
        {
            return NotFound();
        }

        client.Name = request.Name.Trim();
        client.TaxId = request.TaxId.Trim();
        client.Notes = request.Notes?.Trim();

        await dbContext.SaveChangesAsync(cancellationToken);

        var detail = await dbContext.Clients
            .Include(x => x.Configurations)
            .Include(x => x.FilingPeriods)
            .FirstAsync(x => x.Id == clientId, cancellationToken);

        return Ok(ToDetailDto(detail));
    }

    [HttpDelete("{clientId:guid}")]
    [ProducesResponseType(StatusCodes.Status204NoContent)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Delete(Guid clientId, CancellationToken cancellationToken)
    {
        var userId = currentUserService.UserId!.Value;
        var client = await dbContext.FindOwnedClientAsync(clientId, userId, cancellationToken);
        if (client is null)
        {
            return NotFound();
        }

        dbContext.Clients.Remove(client);
        await dbContext.SaveChangesAsync(cancellationToken);

        return NoContent();
    }

    private static ClientDetailDto ToDetailDto(Client client)
    {
        return new ClientDetailDto(
            client.Id,
            client.Name,
            client.TaxId,
            client.Notes,
            client.CreatedAtUtc,
            client.Configurations
                .OrderByDescending(x => x.IsActive)
                .ThenByDescending(x => x.UpdatedAtUtc)
                .Select(x => new ClientConfigDto(x.Id, x.Name, x.PrefillValuesJson, x.TransformationRulesJson, x.IsActive, x.UpdatedAtUtc))
                .ToList(),
            client.FilingPeriods
                .OrderByDescending(x => x.Year)
                .ThenByDescending(x => x.Month)
                .Select(x => new FilingPeriodSummaryDto(x.Id, x.Year, x.Month, x.CreatedAtUtc))
                .ToList());
    }
}
