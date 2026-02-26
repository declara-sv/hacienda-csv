using Accounting.Api.Auth;
using Accounting.Api.Data;
using Accounting.Api.Storage;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Accounting.Api.Controllers;

[ApiController]
[Authorize]
[Route("api/artifacts")]
public sealed class ArtifactsController(
    AppDbContext dbContext,
    ICurrentUserService currentUserService,
    IFileStorage fileStorage) : ControllerBase
{
    [HttpGet("{artifactId:guid}/download")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Download(Guid artifactId, CancellationToken cancellationToken)
    {
        var userId = currentUserService.UserId!.Value;

        var artifact = await dbContext.OutputArtifacts
            .Include(x => x.Client)
            .FirstOrDefaultAsync(x => x.Id == artifactId && x.Client.OwnerUserId == userId, cancellationToken);

        if (artifact is null)
        {
            return NotFound();
        }

        var stream = await fileStorage.OpenReadAsync(new StoredFileReference(
            artifact.StorageProvider,
            artifact.StorageContainer,
            artifact.StoragePath), cancellationToken);

        if (stream is null)
        {
            return NotFound();
        }

        return File(stream, artifact.ContentType, artifact.FileName);
    }
}
