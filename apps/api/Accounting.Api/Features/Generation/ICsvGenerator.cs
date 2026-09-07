namespace Accounting.Api.Features.Generation;

public sealed record GenerationSourceFile(
    Guid? UploadId,
    string OriginalFileName,
    string SourceFileKind,
    long SizeBytes,
    Func<CancellationToken, Task<Stream>> OpenRead);

public sealed record GenerationContext(
    Guid ClientId,
    int Year,
    int Month,
    int Version,
    IReadOnlyList<GenerationSourceFile> Files);

public sealed record GeneratedFile(string FileName, string ContentType, Stream Content);

public interface ICsvGenerator
{
    Task<IReadOnlyList<GeneratedFile>> GenerateAsync(GenerationContext context, CancellationToken cancellationToken);
}
