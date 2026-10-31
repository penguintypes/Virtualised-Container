#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main() {
    char buffer[100];

    char *saved_word[10];
    int count = 0;







    memset(saved_word, 0, sizeof(saved_word));

    for (int i = 0; i < 3; i++) {
        strcpy(buffer, "3");
        saved_word[i] = strdup(buffer);
        printf("[%d]: %s\n", i, saved_word[i]);
    }

    return 0;
}
