#include "aidemo_wrap.h"
// #include "Jieba.hpp"
#include "jieba_utils.h"
// #include "pypinyin.h"
#include "zh_frontend.h"
#include <iostream>
#include <string>
#include <algorithm>
#include <cmath>
#include <cctype>
#include "VoxCommon.h"


struct TtsZh{
    zh_frontend zh;
    // Pypinyin pypinyin;
    map<string, int> symbol_to_id;
};

TtsZh* ttszh_create(){
    try {
        TtsZh *ttszh_=new TtsZh;
        ttszh_->zh=zh_frontend();
        return ttszh_;
    } catch (...) {
        return nullptr;
    }
}

void ttszh_destroy(TtsZh* ttszh){
    delete ttszh;
}

bool ttszh_init_safe(TtsZh* ttszh,const char* dictfile,const char* phasefile,const char* mapfile){
    if (ttszh == nullptr || dictfile == nullptr || phasefile == nullptr || mapfile == nullptr) {
        return false;
    }
    try {
    std::string dict_file(dictfile);
    // std::cout<<dict_file<<std::endl;
    std::string phase_file(phasefile);
    // std::cout<<phase_file<<std::endl;
    std::string mapfile_(mapfile);
    // std::cout<<mapfile<<std::endl;
    pypinyin.Init(dict_file,phase_file);
    // std::cout<<"pypinyin init"<<std::endl;
    std::ifstream file_zh(mapfile_);
    std::string line;
    while (std::getline(file_zh, line)) {
        std::istringstream iss(line);
        std::string str;
        int num;
        iss >> str >> num;
        ttszh->symbol_to_id[str] = num;
    }
    file_zh.close();
    return true;
    } catch (...) {
        return false;
    }
}

void ttszh_init(TtsZh* ttszh,const char* dictfile,const char* phasefile,const char* mapfile){
    (void)ttszh_init_safe(ttszh, dictfile, phasefile, mapfile);
}

int _symbols_to_sequence_zh(const string& s,const map<string,int>& symbol_to_id)
{
    const auto symbol = symbol_to_id.find(s);
    if (symbol != symbol_to_id.end() && s != "_" && s != "~") {
        return symbol->second;
    }
    const auto pause = symbol_to_id.find("sp");
    return pause != symbol_to_id.end() ? pause->second : 0;
}

TtsZhOutput* tts_zh_frontend_preprocess(TtsZh* ttszh_,const char* text){
    if (ttszh_ == nullptr || text == nullptr) {
        return nullptr;
    }
    try {
    // zh_frontend zh;
    std::string text_zh(text);
    // std::cout<<text_zh<<std::endl;
    std::vector<std::vector<float>> sequence_list;
    //解析得到的音素数据
    std::vector<string> result_phonemes;
    //每个拆分的子音素序列中有效数据的长度列表
    std::vector<int> padding_phonemes;
    //音素序列
    std::vector<float> sequence;
    regex RE_DOUHAO_NUM("([0-9])([\\,])([0-9])");        
    std::string text_ = std::regex_replace(text_zh,RE_DOUHAO_NUM,"$1$3"); 
    // std::cout<<text_<<std::endl;
    //文本转拼音
    std::vector<vector<string>> pinyin = ttszh_->zh.get_phonemes(text_,false,true,false,false);
    // for (std::vector<std::string> tt : pinyin) {
    //     for(std::string s:tt){
    //         std::cout<<s<<" ";
    //     }
    // }
    //拼音转音素
    for (std::vector<std::string>& t : pinyin) {
        if (!t.empty() && t.back() == "\n") {
            t.pop_back(); 
        }
        result_phonemes.insert(result_phonemes.end(), t.begin(), t.end());
    }
    //result_phonemes是预处理得到的音素列表，因为fastspeech1模型的输入是定长(1,50)
    //因此，如果一个句子的音素超过50需要拆分成多个50处理
    for(string t : result_phonemes) {
        if (sequence.size()<50)
            sequence.push_back(static_cast<float>(_symbols_to_sequence_zh(t,ttszh_->symbol_to_id)));
        else
        {
            sequence.resize(50,357.0);
            sequence_list.push_back(sequence);
            padding_phonemes.push_back(50);
            sequence.clear();
            sequence.push_back(static_cast<float>(_symbols_to_sequence_zh(t,ttszh_->symbol_to_id)));
        }
    }
    if (!sequence.empty()) {
        const int valid_phoneme_count = static_cast<int>(sequence.size());
        sequence.resize(50,357.0);
        //如果当前序列全部是填充值357，则都是无效的，不将其添加到序列列表
        bool is_all_padding = std::all_of(
            std::begin(sequence), 
            std::end(sequence), 
            [](int item) { return item == 357.0; }
        );
        if (!is_all_padding) {
            padding_phonemes.push_back(valid_phoneme_count);
            sequence_list.push_back(sequence);
        }
        sequence.clear();
    }


    std::vector<float> sequence_all;
    for (const auto& seq : sequence_list) {
        sequence_all.insert(sequence_all.end(), seq.begin(), seq.end());
    }
    // // 遍历并打印 std::vector<int> 中的所有元素
    // std::cout << "Elements in the vector: ";
    // for (const auto& num : sequence_all) {
    //     std::cout << num << " ";
    // }
    // std::cout << std::endl;
    TtsZhOutput* tts_zh_out = (TtsZhOutput *)calloc(1, sizeof(TtsZhOutput));
    if (tts_zh_out == nullptr) {
        return nullptr;
    }
    tts_zh_out[0].size = sequence_all.size();
    if (tts_zh_out->size > 0) {
        tts_zh_out[0].data = (float *)malloc(tts_zh_out->size * sizeof(float));
        if (tts_zh_out->data == nullptr) {
            tts_zh_output_destroy(tts_zh_out);
            return nullptr;
        }
    }
    for (size_t i = 0; i < tts_zh_out[0].size; ++i) {
        tts_zh_out[0].data [i] = sequence_all[i];
    }
    tts_zh_out[0].len_size=padding_phonemes.size();
    if (tts_zh_out->len_size > 0) {
        tts_zh_out[0].len_data=(int *)malloc(tts_zh_out->len_size * sizeof(int));
        if (tts_zh_out->len_data == nullptr) {
            tts_zh_output_destroy(tts_zh_out);
            return nullptr;
        }
    }
    for(size_t i=0;i<tts_zh_out[0].len_size;++i){
        tts_zh_out[0].len_data[i]=padding_phonemes[i];
    }
    return tts_zh_out;
    } catch (...) {
        return nullptr;
    }
}

void tts_zh_output_destroy(TtsZhOutput* output) {
    if (output == nullptr) {
        return;
    }
    free(output->data);
    free(output->len_data);
    free(output);
}

void tts_zh_free_output(void *context)
{
    TtsZhOutput *output = static_cast<TtsZhOutput *>(context);
    if (output == NULL) {
        return;
    }

    free(output->data);
    free(output->len_data);
    free(output);
}

void tts_save_wav(float* wav_data,int wav_len,const char* wav_filename,int sample_rate){
    try {
        // 将数组输入转为vector适配函数输入
        std::vector<float> wav_vector(wav_data, wav_data + wav_len);
        std::string wav_path(wav_filename);
        //当所有音频数据生成完毕，保存成wav文件
        VoxUtil::ExportWAV(wav_path, wav_vector, sample_rate);
    } catch (...) {
        // Do not allow an STL or I/O exception to cross the C ABI boundary.
    }
}
