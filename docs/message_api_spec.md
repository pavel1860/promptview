# Message API Specification

Base path: `/api/messages`

## Endpoints

### Create Message
- **POST** `/`
- Creates a new message in the message log
- **Request Body**:
  ```json
  {
    "role": "string",         // Required: Role of the message sender (user/assistant/system)
    "name": "string",         // Required: Name of the message sender
    "content": "string",      // Required: Content of the message
    "blocks": [{}],          // Optional: Structured blocks in the message
    "extra": {},             // Optional: Extra metadata (default: {})
    "run_id": "string",      // Optional: Run ID for tracking
    "platform_id": "string", // Optional: Platform identifier
    "ref_id": "string"       // Optional: Reference ID
  }
  ```
- **Response** (200 OK):
  ```json
  {
    "id": "integer",
    "created_at": "datetime",
    "role": "string",
    "name": "string",
    "content": "string",
    "blocks": [{}],
    "extra": {},
    "run_id": "string",
    "platform_id": "string",
    "ref_id": "string",
    "branch_order": "integer",
    "branch_id": "integer",
    "turn_id": "integer"
  }
  ```
- **Error Responses**:
  - 400: Bad Request
  - 500: Internal Server Error

### Get Message by ID
- **GET** `/{message_id}`
- Retrieves a specific message by its ID
- **Path Parameters**:
  - `message_id`: integer
- **Response** (200 OK): Same as Create Message response
- **Error Responses**:
  - 404: Message not found
  - 500: Internal Server Error

### List Messages
- **GET** `/`
- Retrieves a list of messages with pagination
- **Query Parameters**:
  - `limit`: integer (default: 10) - Number of messages to return
  - `offset`: integer (default: 0) - Number of messages to skip
  - `session_id`: integer (optional) - Filter by session ID
- **Response** (200 OK): Array of message objects
- **Error Responses**:
  - 400: Bad Request
  - 500: Internal Server Error

### Get Messages in Turn
- **GET** `/turn/{turn_id}`
- Retrieves all messages within a specific turn
- **Path Parameters**:
  - `turn_id`: integer
- **Response** (200 OK): Array of message objects
- **Error Responses**:
  - 400: Bad Request
  - 500: Internal Server Error

### Update Message
- **PATCH** `/{message_id}`
- Updates an existing message
- **Path Parameters**:
  - `message_id`: integer
- **Request Body**:
  ```json
  {
    "role": "string",         // Optional
    "name": "string",         // Optional
    "content": "string",      // Optional
    "blocks": [{}],          // Optional
    "extra": {},             // Optional
    "platform_id": "string", // Optional
    "ref_id": "string"       // Optional
  }
  ```
- **Response** (200 OK): Updated message object
- **Error Responses**:
  - 400: Bad Request
  - 500: Internal Server Error

### Delete Message
- **DELETE** `/{message_id}`
- Deletes a message (currently not implemented)
- **Path Parameters**:
  - `message_id`: integer
- **Response** (501):
  - Not Implemented error

## Notes
- All endpoints require a MessageLog instance which is automatically injected through dependency injection
- The MessageLog instance creates a test session and branch if they don't exist
- The API uses Pydantic models for request/response validation
- All datetime fields are in ISO 8601 format
- Error responses include a detail message explaining the error 