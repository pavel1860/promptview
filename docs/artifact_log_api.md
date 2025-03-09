# Artifact Log API Specification

The Artifact Log API provides endpoints for managing versioned artifacts and their history in a git-like architecture. It allows tracking changes, managing branches, and retrieving historical data.

## Base URL
All endpoints are prefixed with `/artifact_log`

## Headers
The following headers are required for all requests:
- `head_id` (required): The current head turn ID
- `branch_id` (optional): The current branch ID

## Endpoints

### Get All Branches
Retrieves a list of all branches in the artifact log.

```http
GET /branches
```

#### Response
Returns an array of Branch objects with the following structure:
```json
[
  {
    "id": "integer",
    "name": "string",
    "created_at": "datetime",
    "updated_at": "datetime",
    "branch_index": "integer",
    "turn_counter": "integer",
    "forked_from_turn_index": "integer | null",
    "forked_from_branch_id": "integer | null"
  }
]
```

### Get Branch by ID
Retrieves a specific branch by its ID.

```http
GET /branches/{branch_id}
```

#### Parameters
- `branch_id` (path parameter, required): The ID of the branch to retrieve

#### Response
Returns a Branch object with the following structure:
```json
{
  "id": "integer",
  "name": "string",
  "created_at": "datetime",
  "updated_at": "datetime",
  "branch_index": "integer",
  "turn_counter": "integer",
  "forked_from_turn_index": "integer | null",
  "forked_from_branch_id": "integer | null"
}
```

### Get All Turns
Retrieves all turns in the current branch.

```http
GET /all_turns
```

#### Response
Returns an array of Turn objects with the following structure:
```json
[
  {
    "id": "integer",
    "branch_id": "integer",
    "index": "integer",
    "status": "string (STAGED | COMMITTED | REVERTED)",
    "created_at": "datetime",
    "ended_at": "datetime | null",
    "message": "string | null"
  }
]
```

## Error Responses

### 400 Bad Request
Returned when:
- The `head_id` header is missing
- Invalid parameters are provided

### 404 Not Found
Returned when:
- The requested branch or turn does not exist

### 500 Internal Server Error
Returned when:
- An unexpected error occurs during processing

## Models

### Branch
```typescript
{
  id: number;
  name: string;
  created_at: string; // ISO 8601 datetime
  updated_at: string; // ISO 8601 datetime
  branch_index: number;
  turn_counter: number;
  forked_from_turn_index?: number;
  forked_from_branch_id?: number;
}
```

### Turn
```typescript
{
  id: number;
  branch_id: number;
  index: number;
  status: "STAGED" | "COMMITTED" | "REVERTED";
  created_at: string; // ISO 8601 datetime
  ended_at?: string; // ISO 8601 datetime
  message?: string;
}
``` 