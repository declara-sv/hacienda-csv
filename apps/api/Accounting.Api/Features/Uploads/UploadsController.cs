using Accounting.Api.Auth;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Accounting.Api.Features.Uploads;

[ApiController]
[Authorize]
[Route("api/clients/{clientId:guid}/periods/{filingPeriodId:guid}/uploads")]
public sealed class UploadsController(
    UploadsService uploadsService,
    ICurrentUserService currentUserService) : ControllerBase
{
    [HttpGet]
    [ProducesResponseType<IReadOnlyList<UploadDto>>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> List(Guid clientId, Guid filingPeriodId, CancellationToken cancellationToken)
    {
        var uploads = await uploadsService.ListAsync(clientId, filingPeriodId, currentUserService.UserId!.Value, cancellationToken);
        return uploads is null ? NotFound() : Ok(uploads);
    }

    [HttpPost]
    [RequestSizeLimit(20_000_000)]
    [ProducesResponseType<UploadDto>(StatusCodes.Status201Created)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Upload(Guid clientId, Guid filingPeriodId, [FromForm] CreateUploadRequestDto request, CancellationToken cancellationToken)
    {
        if (request.File.Length <= 0)
        {
            return BadRequest(new ValidationProblemDetails(new Dictionary<string, string[]>
            {
                ["file"] = ["El archivo está vacío."],
            }));
        }

        if (!UploadsService.IsValidFileType(request.File.FileName, request.SourceFileKind))
        {
            return BadRequest(new ValidationProblemDetails(new Dictionary<string, string[]>
            {
                ["file"] = ["El tipo de archivo no corresponde al tipo seleccionado (Excel/PDF)."],
            }));
        }

        var upload = await uploadsService.CreateAsync(
            clientId, filingPeriodId, currentUserService.UserId!.Value, request.File, request.SourceFileKind, cancellationToken);

        if (upload is null)
        {
            return NotFound();
        }

        return Created($"/api/clients/{clientId}/periods/{filingPeriodId}/uploads/{upload.Id}", upload);
    }

    [HttpDelete("{uploadId:guid}")]
    [ProducesResponseType(StatusCodes.Status204NoContent)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    public async Task<IActionResult> Delete(Guid clientId, Guid filingPeriodId, Guid uploadId, CancellationToken cancellationToken)
    {
        var outcome = await uploadsService.DeleteAsync(clientId, filingPeriodId, uploadId, currentUserService.UserId!.Value, cancellationToken);

        return outcome switch
        {
            DeleteUploadOutcome.Deleted => NoContent(),
            DeleteUploadOutcome.ReferencedByActiveRun => Conflict(new ProblemDetails
            {
                Title = "El archivo está siendo usado por una generación en curso.",
                Status = StatusCodes.Status409Conflict,
            }),
            _ => NotFound(),
        };
    }
}
