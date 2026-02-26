using System.Text.Json;
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
[Route("api/clients/{clientId:guid}/configs")]
public sealed class ClientConfigsController(AppDbContext dbContext, ICurrentUserService currentUserService) : ControllerBase
{
    [HttpGet]
    [ProducesResponseType<IReadOnlyList<ClientConfigDto>>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> List(Guid clientId, CancellationToken cancellationToken)
    {
        var userId = currentUserService.UserId!.Value;
        var clientExists = await dbContext.Clients.AnyAsync(x => x.Id == clientId && x.OwnerUserId == userId, cancellationToken);
        if (!clientExists)
        {
            return NotFound();
        }

        var configs = await dbContext.ClientConfigs
            .Where(x => x.ClientId == clientId)
            .OrderByDescending(x => x.IsActive)
            .ThenByDescending(x => x.UpdatedAtUtc)
            .Select(x => new ClientConfigDto(x.Id, x.Name, x.PrefillValuesJson, x.TransformationRulesJson, x.IsActive, x.UpdatedAtUtc))
            .ToListAsync(cancellationToken);

        return Ok(configs);
    }

    [HttpPost]
    [ProducesResponseType<ClientConfigDto>(StatusCodes.Status201Created)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Create(Guid clientId, CreateClientConfigRequestDto request, CancellationToken cancellationToken)
    {
        var userId = currentUserService.UserId!.Value;
        var client = await dbContext.FindOwnedClientAsync(clientId, userId, cancellationToken);
        if (client is null)
        {
            return NotFound();
        }

        if (!IsValidJson(request.PrefillValuesJson) || !IsValidJson(request.TransformationRulesJson))
        {
            return BadRequest(new ValidationProblemDetails(new Dictionary<string, string[]>
            {
                ["json"] = ["PrefillValuesJson y TransformationRulesJson deben ser JSON válido."],
            }));
        }

        if (request.IsActive)
        {
            var existingActive = await dbContext.ClientConfigs.Where(x => x.ClientId == clientId && x.IsActive).ToListAsync(cancellationToken);
            foreach (var item in existingActive)
            {
                item.IsActive = false;
                item.UpdatedAtUtc = DateTime.UtcNow;
            }
        }

        var config = new ClientConfig
        {
            ClientId = clientId,
            Name = request.Name.Trim(),
            PrefillValuesJson = request.PrefillValuesJson,
            TransformationRulesJson = request.TransformationRulesJson,
            IsActive = request.IsActive,
            UpdatedAtUtc = DateTime.UtcNow,
        };

        dbContext.ClientConfigs.Add(config);
        await dbContext.SaveChangesAsync(cancellationToken);

        return Created($"/api/clients/{clientId}/configs/{config.Id}", new ClientConfigDto(
            config.Id,
            config.Name,
            config.PrefillValuesJson,
            config.TransformationRulesJson,
            config.IsActive,
            config.UpdatedAtUtc));
    }

    [HttpPut("{configId:guid}")]
    [ProducesResponseType<ClientConfigDto>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Update(Guid clientId, Guid configId, UpdateClientConfigRequestDto request, CancellationToken cancellationToken)
    {
        var userId = currentUserService.UserId!.Value;
        var ownsClient = await dbContext.Clients.AnyAsync(x => x.Id == clientId && x.OwnerUserId == userId, cancellationToken);
        if (!ownsClient)
        {
            return NotFound();
        }

        if (!IsValidJson(request.PrefillValuesJson) || !IsValidJson(request.TransformationRulesJson))
        {
            return BadRequest(new ValidationProblemDetails(new Dictionary<string, string[]>
            {
                ["json"] = ["PrefillValuesJson y TransformationRulesJson deben ser JSON válido."],
            }));
        }

        var config = await dbContext.ClientConfigs.FirstOrDefaultAsync(x => x.Id == configId && x.ClientId == clientId, cancellationToken);
        if (config is null)
        {
            return NotFound();
        }

        if (request.IsActive)
        {
            var existingActive = await dbContext.ClientConfigs
                .Where(x => x.ClientId == clientId && x.IsActive && x.Id != configId)
                .ToListAsync(cancellationToken);

            foreach (var item in existingActive)
            {
                item.IsActive = false;
                item.UpdatedAtUtc = DateTime.UtcNow;
            }
        }

        config.Name = request.Name.Trim();
        config.PrefillValuesJson = request.PrefillValuesJson;
        config.TransformationRulesJson = request.TransformationRulesJson;
        config.IsActive = request.IsActive;
        config.UpdatedAtUtc = DateTime.UtcNow;

        await dbContext.SaveChangesAsync(cancellationToken);

        return Ok(new ClientConfigDto(config.Id, config.Name, config.PrefillValuesJson, config.TransformationRulesJson, config.IsActive, config.UpdatedAtUtc));
    }

    [HttpDelete("{configId:guid}")]
    [ProducesResponseType(StatusCodes.Status204NoContent)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Delete(Guid clientId, Guid configId, CancellationToken cancellationToken)
    {
        var userId = currentUserService.UserId!.Value;
        var ownsClient = await dbContext.Clients.AnyAsync(x => x.Id == clientId && x.OwnerUserId == userId, cancellationToken);
        if (!ownsClient)
        {
            return NotFound();
        }

        var config = await dbContext.ClientConfigs.FirstOrDefaultAsync(x => x.Id == configId && x.ClientId == clientId, cancellationToken);
        if (config is null)
        {
            return NotFound();
        }

        dbContext.ClientConfigs.Remove(config);
        await dbContext.SaveChangesAsync(cancellationToken);

        var hasActive = await dbContext.ClientConfigs.AnyAsync(x => x.ClientId == clientId && x.IsActive, cancellationToken);
        if (!hasActive)
        {
            var fallback = await dbContext.ClientConfigs
                .Where(x => x.ClientId == clientId)
                .OrderByDescending(x => x.UpdatedAtUtc)
                .FirstOrDefaultAsync(cancellationToken);

            if (fallback is not null)
            {
                fallback.IsActive = true;
                fallback.UpdatedAtUtc = DateTime.UtcNow;
                await dbContext.SaveChangesAsync(cancellationToken);
            }
        }

        return NoContent();
    }

    private static bool IsValidJson(string? json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            return true;
        }

        try
        {
            JsonDocument.Parse(json);
            return true;
        }
        catch
        {
            return false;
        }
    }
}
