import json

# Read the iab-taxonomy.json file
with open('iab-taxonomy.json', 'r', encoding='utf-8') as f:
    taxonomy = json.load(f)

# Create the mapping: cluster_id -> list of (iab_code, iab_keywords)
cluster_mapping = {}

for cluster in taxonomy['clusters']:
    cluster_id = cluster['cluster_id']
    cluster_name = cluster['cluster_name']
    
    # Initialize cluster entry
    cluster_mapping[cluster_id] = {
        'cluster_name': cluster_name,
        'categories': []
    }
    
    # Add each category's iab_code and iab_keywords
    for category in cluster['categories']:
        category_entry = {
            'iab_code': category['iab_code'],
            'iab_description': category['iab_description'],
            'iab_keywords': category['iab_keywords']
        }
        cluster_mapping[cluster_id]['categories'].append(category_entry)

# Save the mapping to a new file
with open('cluster_iab_mapping.json', 'w', encoding='utf-8') as f:
    json.dump(cluster_mapping, f, ensure_ascii=False, indent=2)

print("Mapping created successfully!")
print("\nCluster Mapping Summary:")
for cluster_id, data in cluster_mapping.items():
    print(f"\nCluster {cluster_id}: {data['cluster_name']}")
    for category in data['categories']:
        print(f"  - IAB Code: {category['iab_code']} ({category['iab_description']})")
        print(f"    Keywords: {', '.join(category['iab_keywords'][:3])}...")
