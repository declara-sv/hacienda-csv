using System.Text;
using Accounting.Api.Auth;
using Accounting.Api.Configuration;
using Accounting.Api.Data;
using Accounting.Api.Domain.Entities;
using Accounting.Api.Storage;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Identity;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;

DotEnvLoader.TryLoad(Path.Combine(Directory.GetCurrentDirectory(), ".env"));

var builder = WebApplication.CreateBuilder(args);

builder.Services.Configure<JwtOptions>(builder.Configuration.GetSection(JwtOptions.SectionName));
builder.Services.Configure<StorageOptions>(builder.Configuration.GetSection(StorageOptions.SectionName));

builder.Services.AddOptions<Accounting.Api.Features.Generation.GenerationOptions>()
    .Bind(builder.Configuration.GetSection(Accounting.Api.Features.Generation.GenerationOptions.SectionName))
    .ValidateDataAnnotations()
    .ValidateOnStart();

var connectionString = builder.Configuration.GetConnectionString("Postgres")
    ?? throw new InvalidOperationException("ConnectionStrings:Postgres es requerido.");

builder.Services.AddDbContext<AppDbContext>(options => options.UseNpgsql(connectionString));

builder.Services.AddHttpContextAccessor();
builder.Services.AddScoped<ICurrentUserService, CurrentUserService>();
builder.Services.AddScoped<ITokenService, TokenService>();
builder.Services.AddScoped<IPasswordHasher<AppUser>, PasswordHasher<AppUser>>();

var storageOptions = builder.Configuration.GetSection(StorageOptions.SectionName).Get<StorageOptions>() ?? new StorageOptions();
builder.Services.AddSingleton<IFileStorage>(_ =>
{
    return string.Equals(storageOptions.Provider, "AzureBlob", StringComparison.OrdinalIgnoreCase)
        ? new AzureBlobFileStorage(Microsoft.Extensions.Options.Options.Create(storageOptions))
        : new LocalFileStorage(Microsoft.Extensions.Options.Options.Create(storageOptions));
});

var jwtOptions = builder.Configuration.GetSection(JwtOptions.SectionName).Get<JwtOptions>() ?? new JwtOptions();
var signingKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwtOptions.SigningKey));

builder.Services
    .AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer = true,
            ValidIssuer = jwtOptions.Issuer,
            ValidateAudience = true,
            ValidAudience = jwtOptions.Audience,
            ValidateIssuerSigningKey = true,
            IssuerSigningKey = signingKey,
            ValidateLifetime = true,
            ClockSkew = TimeSpan.FromSeconds(30),
        };
    });

builder.Services.AddAuthorization();

builder.Services.AddCors(options =>
{
    options.AddPolicy("web", policy =>
    {
        var allowedOrigins = builder.Configuration.GetSection("Cors:AllowedOrigins").Get<string[]>() ??
            ["http://localhost:3000", "http://localhost:5173"];
        var allowVercelSubdomains = builder.Configuration.GetValue("Cors:AllowVercelSubdomains", true);

        var allowedOriginSet = new HashSet<string>(allowedOrigins, StringComparer.OrdinalIgnoreCase);

        policy.AllowAnyMethod()
            .AllowAnyHeader()
            .AllowCredentials()
            .SetIsOriginAllowed(origin =>
            {
                if (string.IsNullOrWhiteSpace(origin))
                {
                    return false;
                }

                if (allowedOriginSet.Contains(origin))
                {
                    return true;
                }

                if (!allowVercelSubdomains)
                {
                    return false;
                }

                if (!Uri.TryCreate(origin, UriKind.Absolute, out var uri))
                {
                    return false;
                }

                return uri.Scheme == Uri.UriSchemeHttps &&
                       uri.Host.EndsWith(".vercel.app", StringComparison.OrdinalIgnoreCase);
            });
    });
});

builder.Services
    .AddControllers()
    .AddJsonOptions(options =>
    {
        options.JsonSerializerOptions.Converters.Add(new System.Text.Json.Serialization.JsonStringEnumConverter());
    });

builder.Services.AddScoped<Accounting.Api.Features.Uploads.UploadsService>();
builder.Services.AddScoped<Accounting.Api.Features.Generation.GenerationRunsService>();
builder.Services.AddScoped<Accounting.Api.Features.Generation.GenerationRunProcessor>();
builder.Services.AddSingleton<Accounting.Api.Features.Generation.ICsvGenerator, Accounting.Api.Features.Generation.PlaceholderCsvGenerator>();
builder.Services.AddHostedService<Accounting.Api.Features.Generation.GenerationWorker>();

builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

builder.Services.AddProblemDetails();

var app = builder.Build();

app.UseExceptionHandler();
app.UseStatusCodePages();

var enableSwagger = app.Environment.IsDevelopment() || app.Configuration.GetValue<bool>("Features:EnableSwagger");
if (enableSwagger)
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseCors("web");
app.UseAuthentication();
app.UseAuthorization();

app.MapGet("/", () => Results.Ok(new
{
    service = "Accounting.Api",
    status = "ok",
    environment = app.Environment.EnvironmentName,
}));
app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

app.MapControllers();

app.Run();

public partial class Program;
