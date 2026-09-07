using System.Text;

namespace Accounting.Api.Features.Generation;

/// <summary>
/// Temporary generator: one row per included source file. Replace with the real
/// Hacienda parser behind <see cref="ICsvGenerator"/>; nothing else needs to change.
/// </summary>
public sealed class PlaceholderCsvGenerator : ICsvGenerator
{
    public Task<IReadOnlyList<GeneratedFile>> GenerateAsync(GenerationContext context, CancellationToken cancellationToken)
    {
        var builder = new StringBuilder();
        builder.AppendLine("cliente_id,anio,mes,version,archivo_origen,tipo,tamano_bytes");
        foreach (var file in context.Files)
        {
            builder.AppendLine($"{context.ClientId},{context.Year},{context.Month},{context.Version},\"{file.OriginalFileName.Replace("\"", "\"\"")}\",{file.SourceFileKind},{file.SizeBytes}");
        }

        var bytes = Encoding.UTF8.GetBytes(builder.ToString());
        var fileName = $"resultado_{context.Year:D4}_{context.Month:D2}_v{context.Version}.csv";
        IReadOnlyList<GeneratedFile> result = [new GeneratedFile(fileName, "text/csv", new MemoryStream(bytes))];
        return Task.FromResult(result);
    }
}
