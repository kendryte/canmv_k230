all: conf mconf nconf

common-objs = symbol.o util.o menu.o expr.o confdata.o preprocess.o parser.tab.o lexer.lex.o
conf-objs = conf.o $(common-objs)
mconf-objs = mconf.o $(common-objs) lxdialog/util.o lxdialog/inputbox.o lxdialog/menubox.o lxdialog/textbox.o lxdialog/checklist.o lxdialog/yesno.o
nconf-objs = nconf.o nconf.gui.o $(common-objs)


conf: $(conf-objs)
	gcc $(conf-objs) -o conf

mconf: $(mconf-objs)
	gcc $(mconf-objs) -lncurses -o mconf

nconf: $(nconf-objs)
	gcc $(nconf-objs) -lpanel -lmenu -lncurses -o nconf

%.o: %.c
	gcc -c $^ -o $@

parser.tab.c: parser.y
	bison -o $@ --defines=parser.tab.h -t -l $^

lexer.lex.c: lexer.l
	flex -o $@ -L $^

.PHONY: clean
clean:
	rm -rf conf mconf nconf parser.tab.c parser.tab.h lexer.lex.c $(conf-objs) $(mconf-objs) $(nconf-objs)
