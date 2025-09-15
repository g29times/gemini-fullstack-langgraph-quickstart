curl --request POST \
     --url https://api.voyageai.com/v1/rerank \
     --header "Authorization: Bearer $VOYAGE_API_KEY" \
     --header "content-type: application/json" \
     --data '
{
  "query": "Sample query",
  "documents": [
    "Sample document 1",
    "Sample document 2"
  ],
  "model": "rerank-2.5-lite"
}
'


RESPONSE

{
  "object": "list",
  "data": [
    {
      "relevance_score": 0.455078125,
      "index": 0
    },
    {
      "relevance_score": 0.439453125,
      "index": 1
    }
  ],
  "model": "rerank-2.5-lite",
  "usage": {
    "total_tokens": 8
  }
}

---

Rerankers
post
https://api.voyageai.com/v1/rerank
Voyage reranker endpoint receives as input a query, a list of documents, and other arguments such as the model name, and returns a response containing the reranking results.

Body Params
query
string
required
The query as a string. The query can contain a maximum of 8,000 tokens for rerank-2.5 and rerank-2.5-lite; 4,000 tokens for rerank-2; 2,000 tokens for rerank-2-lite and rerank-1; and 1,000 tokens for rerank-lite-1.

documents
array of strings
required
The documents to be reranked as a list of strings.

The number of documents cannot exceed 1,000.
The sum of the number of tokens in the query and the number of tokens in any single document cannot exceed 32,000 for rerank-2.5 and rerank-2.5-lite; 16,000 for rerank-2; 8,000 for rerank-2-lite and rerank-1; and 4,000 for rerank-lite-1.
The total number of tokens, defined as "the number of query tokens × the number of documents + sum of the number of tokens in all documents", cannot exceed 600K for rerank-2.5, rerank-2.5-lite, rerank-2 and rerank-2-lite; and 300K for rerank-1 and rerank-lite-1. Please see our FAQ.
model
string
required
Name of the model. Recommended options: rerank-2.5, rerank-2.5-lite.

top_k
integer | null
Defaults to null
The number of most relevant documents to return. If not specified, the reranking results of all documents will be returned.

return_documents
boolean
Defaults to false
Whether to return the documents in the response. Defaults to false.

If false, the API will return a list of {"index", "relevance_score"} where "index" refers to the index of a document within the input list.
If true, the API will return a list of {"index", "document", "relevance_score"} where "document" is the corresponding document from the input list.
truncation
boolean
Defaults to true
Whether to truncate the input to satisfy the "context length limit" on the query and the documents. Defaults to true.

If true, the query and documents will be truncated to fit within the context length limit, before processed by the reranker model.
If false, an error will be raised when the query exceeds 8,000 tokens for rerank-2.5 and rerank-2.5-lite; 4,000 tokens for rerank-2; 2,000 tokens rerank-2-lite and rerank-1; and 1,000 tokens for rerank-lite-1, or the sum of the number of tokens in the query and the number of tokens in any single document exceeds 32,000 for rerank-2.5 and rerank-2.5-lite; 16,000 for rerank-2; 8,000 for rerank-2-lite and rerank-1; and 4,000 for rerank-lite-1.
Responses

200
Success

Response body
object
object
string
The object type, which is always list.

data
array of objects
An array of the reranking results, sorted by the descending order of relevance scores.

object
index
integer
The index of the document in the input list.

relevance_score
number
The relevance score of the document with respect to the query.

document
string
The document string. Only returned when return_documents is set to true.

model
string
Name of the model.

usage
object
total_tokens
integer
The total number of tokens used for computing the reranking.


4XX
Client error

This indicates an issue with the request format or frequency. Please see our Error Codes guide.

5XX
Server Error

This indicates our servers are experiencing high traffic or having an unexpected issue. Please see our Error Codes guide.