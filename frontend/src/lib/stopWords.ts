/**
 * Stop words excluded from graph search and tool routing matching.
 * Mirrors _STOP_WORDS in services/graph_query.py.
 */
export const STOP_WORDS = new Set([
  // Articles
  "a", "an", "the",
  // Prepositions
  "about", "above", "across", "after", "against", "along", "among",
  "around", "at", "before", "behind", "below", "beneath", "beside",
  "between", "beyond", "by", "down", "during", "for", "from", "in",
  "inside", "into", "like", "near", "of", "off", "on", "onto",
  "out", "outside", "over", "past", "since", "through", "to",
  "toward", "under", "underneath", "until", "unto", "up", "upon",
  "via", "with", "within", "without",
  // Conjunctions
  "and", "but", "or", "nor", "yet", "so",
  // Pronouns
  "i", "me", "my", "mine", "we", "us", "our", "ours", "you", "your",
  "yours", "he", "him", "his", "she", "her", "hers", "it", "its",
  "they", "them", "their", "theirs", "who", "whom", "whose",
  // Demonstratives
  "this", "that", "these", "those",
  // Quantifiers
  "all", "any", "both", "each", "few", "more", "most", "other",
  "some", "such",
  // Verbs (common but low signal)
  "am", "is", "are", "was", "were", "be", "been", "being",
  "have", "has", "had", "do", "does", "did",
  "can", "could", "will", "would", "shall", "should", "may", "might",
  "must", "ought", "need", "want", "use", "using", "get", "got",
  // Question words
  "how", "what", "when", "where", "which", "why",
  // Misc low-signal
  "just", "also", "only", "very", "even", "still", "already",
  "really", "quite", "much", "many", "lot", "too",
  "no", "not", "never", "nothing", "nowhere",
  "here", "there", "then", "once",
]);

export function filterStopWords(words: string[]): string[] {
  return words.filter((w) => w.length >= 2 && !STOP_WORDS.has(w));
}
