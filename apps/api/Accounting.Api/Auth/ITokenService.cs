using Accounting.Api.Domain.Entities;
using Accounting.Api.DTOs.Auth;

namespace Accounting.Api.Auth;

public interface ITokenService
{
    Task<AuthResponseDto> CreateTokenPairAsync(AppUser user, CancellationToken cancellationToken = default);
    Task<AuthResponseDto?> RefreshAsync(string refreshToken, CancellationToken cancellationToken = default);
    Task RevokeRefreshTokenAsync(string refreshToken, CancellationToken cancellationToken = default);
}
