#include <string>  
#include <vector>
#include <regex>

#include "pinyin_utils.h"
#include "char_convert.h"
#include "text_normalization.h"
#include "jieba_utils.h"
#include "zh_frontend.h"



using namespace std;



zh_frontend::zh_frontend()
{
    this->must_erhua = {
        "小院儿", "胡同儿", "范儿", "老汉儿", "撒欢儿", "寻老礼儿", "妥妥儿"
    };
    this->not_erhua = {
        "虐儿", "为儿", "护儿", "瞒儿", "救儿", "替儿", "有儿", "一儿", "我儿", "俺儿", "妻儿",
        "拐儿", "聋儿", "乞儿", "患儿", "幼儿", "孤儿", "婴儿", "婴幼儿", "连体儿", "脑瘫儿",
        "流浪儿", "体弱儿", "混血儿", "蜜雪儿", "舫儿", "祖儿", "美儿", "应采儿", "可儿", "侄儿",
        "孙儿", "侄孙儿", "女儿", "男儿", "红孩儿", "花儿", "虫儿", "马儿", "鸟儿", "猪儿", "猫儿",
        "狗儿"
    };
    this->punc = {"：","，","；","。","？","！","“","”","‘","’","'",":",",",";",".","?","!"};
}

void zh_frontend::_merge_erhua(vector<string>& initials,vector<string>& finals,string word,string pos) {
        if (this->must_erhua.find(word) == this->must_erhua.end() &&
            (this->not_erhua.find(word) != this->not_erhua.end() || pos == "a" ||
             pos == "j" || pos == "nr")) {
            return;
        }
        // "……" 等情况直接返回
        if (finals.size() != word.size()/3) {
            return;
        }
        assert(finals.size() == word.size()/3);
        vector<string> new_initials;
        vector<string> new_finals;
        for (int i = 0; i < finals.size(); i++) {
            if (i == finals.size() - 1 && word.substr(i*3,3) == "儿" &&
                (finals[i] == "er2" || finals[i] == "er5") &&
                this->not_erhua.find(word.substr(word.size() - 2*3)) ==
                    this->not_erhua.end() &&
                !new_finals.empty()) {
                new_finals.back() =
                    new_finals.back().substr(0, new_finals.back().size() - 1) +
                    "r" + new_finals.back().back();
            } else {
                new_finals.push_back(finals[i]);
                new_initials.push_back(initials[i]);
            }
        }
        initials = new_initials;
        finals = new_finals;
        return;
    }

vector<vector<string>> zh_frontend::get_initials_finals(string word) {
    vector<vector<string>> initials_finals;
    vector<string> initials;
    vector<string> finals;
    vector<vector<string>> orig_initials_finals = pypinyin.lazy_pinyin(word, Style::SHENGMU_YUNMU,false,"default",true);
    
    vector<string> orig_initials = orig_initials_finals[0];
    vector<string> orig_finals = orig_initials_finals[1];



    for (int i = 0; i < orig_initials.size(); i++) {
        string c = orig_initials[i];
        string v = orig_finals[i];
        if (regex_match(v, regex("i\\d"))) {
            if (c == "z" || c == "c" || c == "s") {
                v = regex_replace(v, regex("i"), "ii");
            } else if (c == "zh" || c == "ch" || c == "sh" || c == "r") {
                v = regex_replace(v, regex("i"), "iii");
            }
        }
        initials.push_back(c);
        finals.push_back(v);
    }


    initials_finals.push_back(initials);
    initials_finals.push_back(finals);
    return initials_finals;
}
void zh_frontend::splitWord(const string & word, vector<string> & characters)
 {
    int num = word.size();
    int i = 0;
    while(i < num)
     {
         int size = 1;
         if(word[i] & 0x80)
         {
             char temp = word[i];
             temp <<= 1;
             do{
                 temp <<= 1;
                 ++size;
             }while(temp & 0x80);
         }
         string subWord;
         subWord = word.substr(i, size);
         characters.push_back(subWord);
         i += size;
     }
}


vector<vector<string>> zh_frontend::_g2p_fix(vector<string> sentences,
                                             bool merge_sentences,
                                             bool with_erhua) {
    // Keep the existing character-based pronunciation policy. Erhua and word-level
    // tone sandhi are not enabled by this frontend, even when with_erhua is true.
    (void)with_erhua;
    constexpr size_t kMaxGroupSize = 40;
    static const regex english_letters("[a-zA-Z]+");
    vector<vector<string>> phones_list;

    for (const auto &sentence : sentences) {
        const string segment = regex_replace(sentence, english_letters, "");
        vector<string> characters;
        splitWord(segment, characters);
        vector<string> phones;
        size_t group_size = 0;

        for (const auto &word : characters) {
            const auto initials_finals = get_initials_finals(word);
            const auto &initials = initials_finals[0];
            const auto &finals = initials_finals[1];
            // Preserve the original strict <40 grouping before encoder chunking.
            if (group_size > 0 && group_size + initials.size() >= kMaxGroupSize) {
                if (!phones.empty()) {
                    phones_list.push_back(std::move(phones));
                    phones.clear();
                }
                group_size = 0;
            }
            for (size_t i = 0; i < initials.size(); ++i) {
                if (!initials[i].empty()) {
                    phones.push_back(tone_modifier.find_string(initials[i], punc)
                                     ? "sp" : initials[i]);
                }
                if (!finals[i].empty() && !tone_modifier.find_string(finals[i], punc)) {
                    phones.push_back(finals[i]);
                }
            }
            group_size += initials.size();
        }
        if (!phones.empty()) {
            phones_list.push_back(std::move(phones));
        }
    }

    if (merge_sentences) {
        vector<string> merged;
        for (const auto &phones : phones_list) {
            merged.insert(merged.end(), phones.begin(), phones.end());
        }
        if (!merged.empty() && merged.back() == "sp") {
            merged.pop_back();
        }
        phones_list.clear();
        if (!merged.empty()) {
            phones_list.push_back(std::move(merged));
        }
    }
    return phones_list;
}

vector<vector<string>> zh_frontend::get_phonemes(string sentence,
                                                 bool merge_sentences,
                                                 bool with_erhua,
                                                 bool robot,
                                                 bool print_info) {
    if (print_info) {
        cout << "get_phonemes:" << sentence << endl;
    }
    return _g2p_fix(normalize(sentence), merge_sentences, with_erhua);
}
