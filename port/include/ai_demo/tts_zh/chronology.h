#ifndef CHRONOLOGY_H
#define CHRONOLOGY_H

#include <iostream>
#include <regex>
#include <string>  
#include <sstream>
#include <map>
#include <vector>
#include <locale>
#include <assert.h>
#include <wchar.h>
#include <codecvt>



using namespace std;



// Build each pattern once on first use; share it across translation units.
inline const std::regex &RE_DATE() {
    static const std::regex value(R"((\d{4})年((0?[1-9]|1[0-2])月)?((((1|2)[0-9])|30|31|(0?[1-9]))([日号]))?)");
    return value;
}
// # 用 / 或者 - 分隔的 YY/MM/DD 或者 YY-MM-DD 日期
inline const std::regex &RE_DATE2() {
    static const std::regex value(R"((\d{4})([- /.])(0?[1-9]|1[012])\2([12][0-9]|3[01]|0?[1-9]))");
    return value;
}

// # 时刻表达式
inline const std::regex &RE_TIME() {
    static const std::regex value(R"(([0-1]?[0-9]|2[0-3]):([0-5][0-9])(:([0-5][0-9]))?)");
    return value;
}

// 时间范围，如8:30-12:30
inline const std::regex &RE_TIME_RANGE() {
    static const std::regex value(R"(([0-1]?[0-9]|2[0-3]):([0-5][0-9])(:([0-5][0-9]))?(~|-)([0-1]?[0-9]|2[0-3]):([0-5][0-9])(:([0-5][0-9]))?)");
    return value;
}

string replace_date(smatch match);
string replace_date2(smatch match);
string replace_time(smatch match);
#endif



