#include <gtest/gtest.h>

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <set>
#include <sstream>
#include <string>
#include <vector>

namespace fs = std::filesystem;

namespace {

struct CatalogEntry {
    std::string rel_path;
    std::string suggestion;
    std::string priority;
};

std::string trim(const std::string &input) {
    const std::string whitespace = " \t\r\n";
    const size_t begin = input.find_first_not_of(whitespace);
    if (begin == std::string::npos) {
        return "";
    }
    const size_t end = input.find_last_not_of(whitespace);
    return input.substr(begin, end - begin + 1);
}

std::string strip_backticks(const std::string &input) {
    if (input.size() >= 2 && input.front() == '`' && input.back() == '`') {
        return input.substr(1, input.size() - 2);
    }
    return input;
}

std::vector<std::string> split_pipe_columns(const std::string &line) {
    std::vector<std::string> out;
    std::string current;
    for (char ch : line) {
        if (ch == '|') {
            out.push_back(current);
            current.clear();
        } else {
            current.push_back(ch);
        }
    }
    out.push_back(current);
    return out;
}

const fs::path &source_root() {
    static const fs::path kRoot = fs::path(CANMV_SOURCE_ROOT);
    return kRoot;
}

const fs::path &unit_test_root() {
    static const fs::path kRoot = fs::path(CANMV_UNIT_TEST_ROOT);
    return kRoot;
}

std::vector<CatalogEntry> load_catalog_entries() {
    const fs::path catalog = unit_test_root() / "ALL_SOURCE_UNIT_TEST_SUGGESTIONS.md";
    std::ifstream in(catalog);
    if (!in.is_open()) {
        throw std::runtime_error("Failed to open catalog file: " + catalog.string());
    }

    std::vector<CatalogEntry> entries;
    std::string line;
    while (std::getline(in, line)) {
        if (line.rfind("| `", 0) != 0) {
            continue;
        }

        const std::vector<std::string> cols = split_pipe_columns(line);
        if (cols.size() < 5) {
            continue;
        }

        CatalogEntry entry;
        entry.rel_path = strip_backticks(trim(cols[1]));
        entry.suggestion = trim(cols[2]);
        entry.priority = trim(cols[3]);

        if (!entry.rel_path.empty()) {
            entries.push_back(entry);
        }
    }

    return entries;
}

std::set<std::string> enumerate_actual_sources() {
    std::set<std::string> actual;

    for (const auto &item : fs::recursive_directory_iterator(source_root())) {
        if (!item.is_regular_file()) {
            continue;
        }

        const fs::path p = item.path();
        const std::string ext = p.extension().string();
        if (ext != ".c" && ext != ".cc" && ext != ".cpp" && ext != ".h" && ext != ".hpp" && ext != ".py") {
            continue;
        }

        const std::string rel = fs::relative(p, source_root()).generic_string();
        if (rel.rfind("unit_test/", 0) == 0) {
            continue;
        }
        if (rel.rfind("micropython/mpy-cross/build/", 0) == 0) {
            continue;
        }

        actual.insert(rel);
    }

    return actual;
}

std::string summarize_paths(const std::vector<std::string> &paths) {
    std::ostringstream oss;
    const size_t limit = std::min<size_t>(paths.size(), 15);
    for (size_t i = 0; i < limit; ++i) {
        oss << "\n  - " << paths[i];
    }
    if (paths.size() > limit) {
        oss << "\n  ... (" << (paths.size() - limit) << " more)";
    }
    return oss.str();
}

}  // namespace

TEST(AllSourceCatalogTest, CatalogCoversEverySourceFile) {
    const std::vector<CatalogEntry> entries = load_catalog_entries();
    ASSERT_FALSE(entries.empty()) << "Catalog has no source entries";

    std::set<std::string> catalog_sources;
    for (const auto &entry : entries) {
        catalog_sources.insert(entry.rel_path);
    }

    const std::set<std::string> actual_sources = enumerate_actual_sources();

    std::vector<std::string> missing_in_catalog;
    std::vector<std::string> missing_in_tree;

    for (const auto &src : actual_sources) {
        if (catalog_sources.find(src) == catalog_sources.end()) {
            missing_in_catalog.push_back(src);
        }
    }

    for (const auto &src : catalog_sources) {
        if (actual_sources.find(src) == actual_sources.end()) {
            missing_in_tree.push_back(src);
        }
    }

    EXPECT_TRUE(missing_in_catalog.empty())
        << "Sources missing from catalog:" << summarize_paths(missing_in_catalog);
    EXPECT_TRUE(missing_in_tree.empty())
        << "Catalog entries not found in source tree:" << summarize_paths(missing_in_tree);
}

TEST(AllSourceCatalogTest, CatalogEntriesContainValidMetadata) {
    const std::vector<CatalogEntry> entries = load_catalog_entries();
    ASSERT_FALSE(entries.empty());

    std::set<std::string> seen;
    for (const auto &entry : entries) {
        SCOPED_TRACE(entry.rel_path);

        EXPECT_FALSE(entry.rel_path.empty());
        EXPECT_FALSE(entry.suggestion.empty());
        EXPECT_TRUE(entry.priority == "High" || entry.priority == "Medium" || entry.priority == "Low")
            << "Unexpected priority: " << entry.priority;

        EXPECT_TRUE(seen.insert(entry.rel_path).second) << "Duplicate catalog entry";
    }
}

TEST(AllSourceCatalogTest, CatalogEntryCountMatchesSourceCount) {
    const std::vector<CatalogEntry> entries = load_catalog_entries();
    ASSERT_FALSE(entries.empty());

    const std::set<std::string> actual_sources = enumerate_actual_sources();
    EXPECT_EQ(entries.size(), actual_sources.size())
        << "Catalog entry count does not match actual source count";
}

TEST(AllSourceCatalogTest, EveryCatalogEntryPointsToReadableSourceFile) {
    const std::vector<CatalogEntry> entries = load_catalog_entries();
    ASSERT_FALSE(entries.empty());

    for (const auto &entry : entries) {
        SCOPED_TRACE(entry.rel_path);

        const fs::path full_path = source_root() / entry.rel_path;
        ASSERT_TRUE(fs::exists(full_path)) << "Source file does not exist";
        ASSERT_TRUE(fs::is_regular_file(full_path)) << "Source path is not a regular file";

        const std::string ext = full_path.extension().string();
        EXPECT_TRUE(ext == ".c" || ext == ".cc" || ext == ".cpp" || ext == ".h" || ext == ".hpp" || ext == ".py")
            << "Unexpected source extension: " << ext;

        std::ifstream in(full_path);
        ASSERT_TRUE(in.is_open()) << "Unable to open source file";
        in.peek();
        EXPECT_TRUE(in.good() || in.eof()) << "Unable to read source file";
    }
}
