using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Accounting.Api.Tests.Infrastructure;

public sealed record IdResponse(Guid Id);

public sealed record AuthResponse(string AccessToken, string RefreshToken);

public static class ApiClientExtensions
{
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web)
    {
        Converters = { new JsonStringEnumConverter() },
    };

    public static async Task<HttpClient> RegisterAndLoginAsync(this ApiFactory factory, string? email = null)
    {
        var client = factory.CreateClient();
        email ??= $"user-{Guid.NewGuid():N}@test.local";
        var register = await client.PostAsJsonAsync("/api/auth/register", new
        {
            email,
            password = "Password123!",
            fullName = "Test User",
        }, Json);
        register.EnsureSuccessStatusCode();

        var auth = await register.Content.ReadFromJsonAsync<AuthResponse>(Json)
                   ?? throw new InvalidOperationException("Sin respuesta de registro.");
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", auth.AccessToken);
        return client;
    }

    public static async Task<Guid> CreateClientAsync(this HttpClient client, string name = "Cliente Test")
    {
        var response = await client.PostAsJsonAsync("/api/clients", new
        {
            name,
            taxId = $"NIT-{Random.Shared.Next(100000, 999999)}",
            notes = (string?)null,
        }, Json);
        response.EnsureSuccessStatusCode();
        var body = await response.Content.ReadFromJsonAsync<IdResponse>(Json);
        return body!.Id;
    }

    public static async Task<Guid> CreatePeriodAsync(this HttpClient client, Guid clientId, int year = 2026, int month = 1)
    {
        var response = await client.PostAsJsonAsync($"/api/clients/{clientId}/periods", new { year, month }, Json);
        response.EnsureSuccessStatusCode();
        var body = await response.Content.ReadFromJsonAsync<IdResponse>(Json);
        return body!.Id;
    }

    public static async Task<HttpResponseMessage> UploadFileAsync(
        this HttpClient client,
        Guid clientId,
        Guid periodId,
        string fileName = "factura.pdf",
        string sourceFileKind = "PDF",
        byte[]? content = null)
    {
        content ??= "%PDF-1.4 test"u8.ToArray();
        using var form = new MultipartFormDataContent();
        var file = new ByteArrayContent(content);
        file.Headers.ContentType = new MediaTypeHeaderValue(sourceFileKind == "PDF" ? "application/pdf" : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
        form.Add(file, "file", fileName);
        form.Add(new StringContent(sourceFileKind), "sourceFileKind");
        return await client.PostAsync($"/api/clients/{clientId}/periods/{periodId}/uploads", form);
    }

    public static async Task<T> ReadAsAsync<T>(this HttpResponseMessage response)
    {
        var body = await response.Content.ReadFromJsonAsync<T>(Json);
        return body ?? throw new InvalidOperationException($"Cuerpo vacío para {typeof(T).Name}.");
    }
}
