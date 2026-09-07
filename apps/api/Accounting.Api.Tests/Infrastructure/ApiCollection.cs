namespace Accounting.Api.Tests.Infrastructure;

[CollectionDefinition("api")]
public sealed class ApiCollection : ICollectionFixture<PostgresFixture>;
