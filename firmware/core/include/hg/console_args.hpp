// Quoted console arguments, for commands that take more than one free-form
// value (network names and passwords may hold spaces and quotes).
//
// The rules are ESP-IDF's esp_console_split_argv: spaces separate arguments,
// double quotes group them, and a backslash keeps the next backslash, quote or
// space. The USB console splits a line by those rules before the app sees it,
// so the port quotes the pieces again with quote_arg().
#pragma once

#include <string>
#include <string_view>
#include <vector>

namespace hg {

inline std::vector<std::string> split_args(std::string_view line) {
  std::vector<std::string> out;
  std::string arg;
  bool in_arg = false, quoted = false, escaped = false;
  for (char c : line) {
    if (escaped) {
      if (c == '\\' || c == '"' || c == ' ') arg.push_back(c);
      escaped = false;
    } else if (c == '\\') {
      escaped = in_arg = true;
    } else if (quoted) {
      if (c == '"') {
        out.push_back(std::move(arg));
        arg.clear();
        in_arg = quoted = false;
      } else {
        arg.push_back(c);
      }
    } else if (c == ' ') {
      if (in_arg) out.push_back(std::move(arg));
      arg.clear();
      in_arg = false;
    } else if (c == '"' && !in_arg) {
      in_arg = quoted = true;
    } else {
      arg.push_back(c);
      in_arg = true;
    }
  }
  if (in_arg) out.push_back(std::move(arg));
  return out;
}

inline std::string quote_arg(std::string_view value) {
  std::string out = "\"";
  for (char c : value) {
    if (c == '\\' || c == '"') out.push_back('\\');
    out.push_back(c);
  }
  return out + "\"";
}

}  // namespace hg
