#include <iostream>
#include <string>  
#include <sstream>
#include <algorithm>  
#include <map>
#include <vector>
#include <regex>
#include <locale>
#include <codecvt>
#include "pinyin_utils.h"

#include "char_convert.h"
#include "chronology.h"
#include "constants.h"
#include "num.h"
#include "phonecode.h"
#include "quantifier.h"
#include "constants.h"
#include <chrono>

using namespace std;


vector<string> _split(string text,string lang="zh")
{
    vector<string> text_list;
    //去掉所有空格
    trim(text);

    wstring wtext = to_wide_string(text);
    std::wstring filtered_str;
    // Only for pure Chinese here
    if(lang == "zh")
    { 
        // 过滤掉特殊字符,并将标点符号替换为\n
        
        for (wchar_t c : wtext) {
          
          if((c==L'：') | (c==L'、') | (c==L'，')| (c==L'；') | (c==L'。') | (c== L'？')|(c==L'！') | (c==L',') | (c==L';') | (c==L'?') | (c==L'!') | (c==L'”') | (c==L'’'))
          {
            text = to_byte_string(filtered_str)+'\n';  
            text_list.push_back(text);
            filtered_str = L"";
            continue;
          }
          if (c != L'《' && c != L'》' && c != L'【' && c != L'】' && c != L'（' && c != L'）' && c != L'“' && c != L'”' && c != L'…'&& c != L'\\') {
            filtered_str += c;
          }
        }
        if(filtered_str !=L"")
            text_list.push_back(to_byte_string(filtered_str));


    }
    return text_list;
}


string _post_replace(string sentence) {
    string result;
    result.reserve(sentence.size());

    for (unsigned char c : sentence) {
        if (c == '/') {
            result += "每";
        } else if (c == '~') {
            result += "至";
        } else {
            result.push_back((char)c);
        }
    }

    return result;
}

std::wstring _translate(std::wstring sentence) {
    wstring half;
    for (auto c:sentence) {
        //字符全角转半角
        if (c >= L'Ａ' && c <= L'z')
        {
            half.push_back(c - 65248);
        }
        // //标点全角转半角
        // else if (c >= L'！' && c <= L'～')
        // {
        //     half.push_back(c - 65248);
        // }
        //数字全角转半角
        else if (c >= L'０' && c <= L'９')
        {
            half.push_back(c - 65248);
        }
		else if(c==L'\u3000')	
		{
			
			half.push_back(' ');
		}
        else
        {
            half.push_back(c);
        }
       
    }
    return half;
}


std::string normalize_sentence(std::string sentence) {
    
    wstring wsentence = tranditional_to_simplified(to_wide_string(sentence));
   
    sentence = to_byte_string(_translate(wsentence));    
    sentence = replace(replace_date,sentence,RE_DATE());
    sentence = replace(replace_date2,sentence,RE_DATE2());

    sentence = replace(replace_time,sentence,RE_TIME_RANGE());
    sentence = replace(replace_time,sentence,RE_TIME());
    
    sentence = replace(replace_temperature,sentence,RE_TEMPERATURE());
    sentence = std::regex_replace(sentence,RE_PLUS(),"$1加$3");
    sentence = std::regex_replace(sentence,RE_RATIO(),"$1比$3");

    sentence = replace(replace_frac,sentence,RE_FRAC());
    sentence = replace(replace_percentage,sentence,RE_PERCENTAGE());
    sentence = replace_phonecode_zh(replace_mobile_zh,sentence,RE_MOBILE_PHONE1_zh());
    sentence = replace_phonecode_zh(replace_mobile_zh_,sentence,RE_MOBILE_PHONE2_zh());

    

    sentence = replace_phonecode_zh(replace_phone_zh,sentence,RE_TELEPHONE_zh());
    sentence = replace_phonecode_zh(replace_phone_zh,sentence,RE_NATIONAL_UNIFORM_NUMBER_zh());

    
    sentence = replace(replace_range,sentence,RE_RANGE());
    sentence = replace(replace_number,sentence,RE_DECIMAL_NUM());
    sentence = replace(replace_negative_num,sentence,RE_INTEGER());
    
    
    sentence = replace(replace_positive_quantifier,sentence,RE_POSITIVE_QUANTIFIERS());
    sentence = replace(replace_default_num,sentence,RE_DEFAULT_NUM());
    sentence = replace(replace_number,sentence,RE_NUMBER_());

    sentence = _post_replace(sentence);


    return sentence;
}


std::vector<std::string> normalize(std::string text) {
       std::vector<std::string> sentences = _split(text);
       std::vector<std::string> normalized_sentences;
       for (std::string sent : sentences) {
           normalized_sentences.push_back(normalize_sentence(sent));
       }
       return normalized_sentences;
}
