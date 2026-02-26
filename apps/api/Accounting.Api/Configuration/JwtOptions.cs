namespace Accounting.Api.Configuration;

public sealed class JwtOptions
{
    public const string SectionName = "Jwt";

    public string Issuer { get; set; } = "Accounting.Api";
    public string Audience { get; set; } = "Accounting.Web";
    public string SigningKey { get; set; } = "CAMBIAR_ESTA_LLAVE_EN_PRODUCCION_32+";
    public int AccessTokenMinutes { get; set; } = 20;
    public int RefreshTokenDays { get; set; } = 30;
}
