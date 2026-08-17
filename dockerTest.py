from neo4j import GraphDatabase

# Connection details
URI = "bolt://localhost:7687"
AUTH = ("neo4j", "gladline")

print("Attempting connection to Neo4j...")

try:
    # Initialize driver
    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        # Test connection
        driver.verify_connectivity()
        print("Connected to Neo4j successfully!")

        # Run a test query
        result = driver.execute_query("RETURN 'Neo4j is working!' AS message")
        print(f"Server response: {result.records[0]['message']}")

except Exception as e:
    print(f"❌ ERROR: Could not connect to Neo4j.")
    print(e)