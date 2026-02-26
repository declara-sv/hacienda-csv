using System.ComponentModel.DataAnnotations;

namespace Accounting.Api.DTOs.Auth;

public sealed class RegisterRequestDto
{
    [Required, EmailAddress, MaxLength(320)]
    public string Email { get; init; } = string.Empty;

    [Required, MinLength(8), MaxLength(128)]
    public string Password { get; init; } = string.Empty;

    [Required, MaxLength(200)]
    public string FullName { get; init; } = string.Empty;
}

public sealed class LoginRequestDto
{
    [Required, EmailAddress, MaxLength(320)]
    public string Email { get; init; } = string.Empty;

    [Required, MinLength(8), MaxLength(128)]
    public string Password { get; init; } = string.Empty;
}

public sealed class RefreshRequestDto
{
    [Required, MinLength(30), MaxLength(400)]
    public string RefreshToken { get; init; } = string.Empty;
}

public sealed class LogoutRequestDto
{
    [Required, MinLength(30), MaxLength(400)]
    public string RefreshToken { get; init; } = string.Empty;
}

public sealed record AuthUserDto(Guid Id, string Email, string FullName);

public sealed record AuthResponseDto(
    string AccessToken,
    DateTime AccessTokenExpiresAtUtc,
    string RefreshToken,
    AuthUserDto User);
